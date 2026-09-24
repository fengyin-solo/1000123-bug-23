"""系统设置业务规则：系统参数按版本管理。

- 修改参数只追加「待生效」新版本，当前已生效版本保持不变；
- 生效参数把待生效版本转为已生效，原已生效版本完整保留为历史；
- 回滚参数作废待生效版本，或把已生效版本回退到最近的历史版本；
- 任何动作都不覆盖历史行的取值与生效范围，列表与详情读取同一份版本数据。
"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "setting"
REQUIRED_FIELDS = ["参数编码", "参数名称", "参数值"]
# 随参数固定的描述字段：新版本必须从已生效版本逐字段拷贝，禁止靠残留值串位
SNAPSHOT_FIELDS = ["参数名称", "参数类型", "生效范围"]
ENTRY_FIELDS = ["参数编码", "参数名称", "参数值", "参数类型", "生效范围", "修改人"]

STATUS_EFFECTIVE = "已生效"
STATUS_PENDING = "待生效"
STATUS_ROLLED_BACK = "已回滚"
VALID_STATUSES = [STATUS_EFFECTIVE, STATUS_PENDING, STATUS_ROLLED_BACK]


class SettingService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("参数编码", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        rows = sorted(rows, key=lambda row: int(row.get("id", 0)))
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        # 列表与详情都读 store 里的同一行版本记录，不存在两个口径
        return store.find(MODULE, entry_id)

    def list_history(self, entry_id: int) -> list[dict[str, Any]] | None:
        """返回某条版本所属参数编码下的全部版本，历史取值原样保留。"""
        row = store.find(MODULE, entry_id)
        if row is None:
            return None
        code = row.get("参数编码")
        return sorted(
            (item for item in store.rows(MODULE) if item.get("参数编码") == code),
            key=lambda item: int(item.get("版本", 0)),
        )

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, [f"缺少必填字段：{'、'.join(missing)}"]
        rows = store.rows(MODULE)
        code = str(values.get("参数编码")).strip()
        if any(row.get("参数编码") == code for row in rows):
            return None, [f"参数编码 {code} 已存在，调整取值请使用修改参数"]
        entry = self._build_row(rows, code, values, version=1, status=STATUS_EFFECTIVE)
        rows.append(entry)
        return entry, []

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        row = store.find(MODULE, entry_id)
        if row is None:
            return None, f"系统参数 {entry_id} 不存在或已归档"
        if action == "修改参数":
            return self._modify(row, values or {})
        if action == "生效参数":
            return self._activate(row)
        if action == "回滚参数":
            return self._rollback(row)
        return None, f"动作「{action}」不属于系统设置可执行范围"

    # ---- 动作实现 -------------------------------------------------------

    def _modify(
        self, row: dict[str, Any], values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        code = row["参数编码"]
        versions = self._versions(code)
        if self._find_status(versions, STATUS_PENDING) is not None:
            return None, "该参数已有待生效版本，请先生效或回滚后再修改"
        effective = self._find_status(versions, STATUS_EFFECTIVE)
        if effective is None:
            return None, "该参数缺少已生效版本，无法发起修改"

        new_value = str(values.get("参数值") or "").strip()
        if not new_value:
            return None, "修改参数必须提供新的参数值"
        if new_value == str(effective.get("参数值") or ""):
            return None, "新参数值与当前已生效取值一致，无需修改"

        # 以已生效版本为基准逐字段拷贝快照，提交值只覆盖它对应的那一个字段，
        # 杜绝「取值对得上、生效范围错位」这类串位问题
        snapshot: dict[str, Any] = {field: effective.get(field) for field in SNAPSHOT_FIELDS}
        for field in SNAPSHOT_FIELDS:
            submitted = values.get(field)
            if submitted is not None and str(submitted).strip():
                snapshot[field] = str(submitted).strip()
        snapshot["参数值"] = new_value
        operator = str(values.get("修改人") or effective.get("修改人") or "").strip()
        snapshot["修改人"] = operator

        rows = store.rows(MODULE)
        next_version = max(int(item.get("版本", 0)) for item in versions) + 1
        entry = self._build_row(rows, code, snapshot, version=next_version, status=STATUS_PENDING)
        rows.append(entry)
        return entry, "修改已登记为待生效版本，确认后请执行生效参数"

    def _activate(self, row: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        if row.get("status") != STATUS_PENDING:
            return None, "只有待生效版本才能执行生效参数"
        versions = self._versions(row["参数编码"])
        previous = self._find_status(versions, STATUS_EFFECTIVE)
        if previous is not None:
            # 旧生效版本转历史，行不删除、取值不覆盖
            self._stamp(previous, STATUS_ROLLED_BACK)
        self._stamp(row, STATUS_EFFECTIVE)
        return row, "参数新值已生效，原取值已保留为历史版本"

    def _rollback(self, row: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        status = row.get("status")
        if status == STATUS_PENDING:
            # 作废尚未生效的修改，当前已生效版本原封不动
            self._stamp(row, STATUS_ROLLED_BACK)
            return row, "待生效修改已作废，当前已生效取值保持不变"
        if status == STATUS_EFFECTIVE:
            versions = self._versions(row["参数编码"])
            current_version = int(row.get("版本", 0))
            # 只能恢复「曾经生效过」的历史版本；被作废的待生效版本从未生效，不可恢复。
            # 且只向更早的版本回退，连续回滚沿版本号 v_n -> v_n-1 前进，不会来回跳。
            history = [
                item
                for item in versions
                if item.get("status") == STATUS_ROLLED_BACK
                and item.get("生效过")
                and int(item.get("版本", 0)) < current_version
            ]
            if not history:
                return None, "该参数没有可回滚的历史取值"
            target = max(history, key=lambda item: int(item.get("版本", 0)))
            self._stamp(row, STATUS_ROLLED_BACK)
            self._stamp(target, STATUS_EFFECTIVE)
            return target, "已回滚到最近一次历史取值，原取值已保留为历史版本"
        return None, "历史版本不能再次回滚"

    # ---- 辅助 -----------------------------------------------------------

    def _versions(self, code: str) -> list[dict[str, Any]]:
        return [row for row in store.rows(MODULE) if row.get("参数编码") == code]

    @staticmethod
    def _find_status(
        versions: list[dict[str, Any]], status: str
    ) -> dict[str, Any] | None:
        return next((row for row in versions if row.get("status") == status), None)

    @staticmethod
    def _stamp(row: dict[str, Any], status: str) -> None:
        row["status"] = status
        row["pending"] = status == STATUS_PENDING
        row["abnormal"] = status == STATUS_ROLLED_BACK
        if status == STATUS_EFFECTIVE:
            # 一旦当过生效版本就永久留痕，作废的待生效版本不会被误当成可恢复的历史取值
            row["生效过"] = True

    @staticmethod
    def _build_row(
        all_rows: list[dict[str, Any]],
        code: str,
        values: dict[str, Any],
        *,
        version: int,
        status: str,
    ) -> dict[str, Any]:
        # 显式逐字段落库，缺字段补空串，避免把提交载体里的杂键或旧行残留带进新版本
        entry: dict[str, Any] = {
            "id": max((int(row.get("id", 0)) for row in all_rows), default=0) + 1,
            "版本": version,
        }
        for field in ENTRY_FIELDS:
            entry[field] = str(values.get(field) or "").strip() if field != "参数编码" else code
        entry["status"] = status
        entry["pending"] = status == STATUS_PENDING
        entry["abnormal"] = status == STATUS_ROLLED_BACK
        entry["生效过"] = status == STATUS_EFFECTIVE
        return entry
