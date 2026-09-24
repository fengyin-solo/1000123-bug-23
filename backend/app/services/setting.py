"""系统设置业务规则：参数按版本追加写入，历史取值全程保留。

数据模型：同一个「参数编码」可以对应多条记录，每条记录是一次取值的完整快照
（参数值、生效范围等字段都冗余在记录上，读取时不跨记录拼接，避免取值与范围错位）。

状态流转：
- 修改参数：基于当前已生效版本复制一份完整快照，写入新取值，生成「待生效」新版本，
  原已生效版本保持不动（刷新、重新进入读到的都是同一份已落库数据）。
- 生效参数：待生效版本转为「已生效」，原已生效版本转为「已失效」（历史取值保留）。
- 回滚参数：待生效版本可直接撤销为「已回滚」；已生效版本可回到上一份历史取值，
  回滚同样以新版本落库，任何一份历史记录都不会被覆盖或删除。
"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "setting"
REQUIRED_FIELDS = ["参数编码", "参数名称", "参数值"]
EDITABLE_FIELDS = ["参数名称", "参数值", "参数类型", "生效范围", "修改人"]
ALLOWED_ACTIONS = {"修改参数", "回滚参数", "生效参数"}
# 参数版本特有的状态：被新版本顶替的历史已生效记录。
SUPERSEDED_STATUS = "已失效"

# 种子数据里 pending/abnormal 与 status 不完全一致，首次使用时按 status 校准一次，
# 保证概览卡片与列表状态口径一致。
_seed_normalized = False


def _normalize_seed_rows() -> None:
    global _seed_normalized
    if _seed_normalized:
        return
    _seed_normalized = True
    for row in store.rows(MODULE):
        status = row.get("status")
        row["pending"] = status == "待生效"
        row["abnormal"] = status == "已回滚"


def _snapshot_fields(source: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    """以已生效版本为底，叠加本次提交的字段，产出一份完整快照。

    缺省字段一律从源版本继承，绝不留空或从别的记录借字段，
    这样新版本的「参数值」与「生效范围」始终来自同一份快照。
    """
    snapshot: dict[str, Any] = {}
    for field in EDITABLE_FIELDS:
        submitted = values.get(field)
        snapshot[field] = submitted if submitted is not None and str(submitted).strip() else source.get(field)
    return snapshot


class SettingService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        _normalize_seed_rows()
        rows = list(store.rows(MODULE))
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("参数编码", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        # 同一参数编码：新版本在后，倒序后最新版本排最前，列表与详情看到的是同一条记录。
        rows.sort(key=lambda row: (str(row.get("参数编码", "")), -int(row.get("id", 0))))
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        _normalize_seed_rows()
        return store.find(MODULE, entry_id)

    def _versions_of(self, code: str) -> list[dict[str, Any]]:
        return [row for row in store.rows(MODULE) if str(row.get("参数编码", "")) == code]

    def _find_active(self, code: str) -> dict[str, Any] | None:
        for row in self._versions_of(code):
            if row.get("status") == "已生效":
                return row
        return None

    def _find_pending(self, code: str) -> dict[str, Any] | None:
        for row in self._versions_of(code):
            if row.get("status") == "待生效":
                return row
        return None

    def _latest_history(self, code: str) -> dict[str, Any] | None:
        """最近一份可回滚的历史取值：被新版本顶替的已生效版本（已失效）。

        「已回滚」的是从未启用过的待生效修改，不算历史取值，不能作为回滚目标。
        """
        history = [row for row in self._versions_of(code) if row.get("status") == SUPERSEDED_STATUS]
        return max(history, key=lambda row: int(row.get("id", 0)), default=None)

    def create_entry(
        self, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, list[str], str]:
        _normalize_seed_rows()
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing, ""
        rows = store.rows(MODULE)
        code = str(values.get("参数编码", "")).strip()
        if self._find_active(code) is not None or self._find_pending(code) is not None:
            return None, [], f"参数编码 {code} 已存在，请通过「修改参数」变更取值"
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry["参数编码"] = code
        entry["参数名称"] = values.get("参数名称")
        entry["参数值"] = values.get("参数值")
        for field in ("参数类型", "生效范围", "修改人"):
            entry[field] = values.get(field)
        entry["status"] = "已生效"
        entry["pending"] = False
        entry["abnormal"] = False
        rows.append(entry)
        return entry, [], []

    def _append_version(
        self,
        *,
        code: str,
        fields: dict[str, Any],
        status: str,
        pending: bool,
        abnormal: bool,
    ) -> dict[str, Any]:
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry["参数编码"] = code
        entry.update(fields)
        entry["status"] = status
        entry["pending"] = pending
        entry["abnormal"] = abnormal
        rows.append(entry)
        return entry

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        _normalize_seed_rows()
        values = values or {}
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"系统参数 {entry_id} 不存在或已归档"
        if action not in ALLOWED_ACTIONS:
            return None, f"动作「{action}」不属于系统设置可执行范围"

        code = str(entry.get("参数编码", ""))
        active = self._find_active(code)
        pending = self._find_pending(code)

        if action == "修改参数":
            # 必须基于已生效版本落一份新快照；已有待生效版本时先处理，避免两条待生效串值。
            if active is None:
                return None, f"参数 {code} 没有已生效版本，暂不能修改，请先登记或生效"
            if pending is not None:
                return None, f"参数 {code} 已有待生效的修改，请先生效或回滚后再改"
            new_value = values.get("参数值")
            if new_value is None or not str(new_value).strip():
                return None, "修改参数必须提交新的「参数值」"
            fields = _snapshot_fields(active, values)
            version = self._append_version(
                code=code, fields=fields, status="待生效", pending=True, abnormal=False
            )
            return version, "系统参数修改已登记，待生效后正式启用"

        if action == "生效参数":
            if pending is None:
                return None, f"参数 {code} 没有待生效的修改，无需执行生效"
            if active is not None:
                # 原已生效版本转为历史，记录原样保留（取值、生效范围都不丢）。
                active["status"] = SUPERSEDED_STATUS
                active["pending"] = False
                active["abnormal"] = False
            pending["status"] = "已生效"
            pending["pending"] = False
            pending["abnormal"] = False
            return pending, f"系统参数已生效，参数值为「{pending.get('参数值')}」"

        # 回滚参数：待生效版本直接撤销；已生效/已失效版本则回到最近一份历史取值。
        if entry.get("status") == "待生效":
            entry["status"] = "已回滚"
            entry["pending"] = False
            entry["abnormal"] = True
            return entry, "待生效修改已回滚撤销，当前仍沿用原已生效取值"

        if pending is not None and entry.get("status") != "待生效":
            return None, f"参数 {code} 存在待生效修改，请先回滚待生效版本"
        history = self._latest_history(code)
        if history is None:
            return None, f"参数 {code} 没有可回滚的历史取值"
        if active is not None:
            active["status"] = SUPERSEDED_STATUS
            active["pending"] = False
            active["abnormal"] = False
        fields = _snapshot_fields(history, values)
        version = self._append_version(
            code=code, fields=fields, status="已生效", pending=False, abnormal=False
        )
        return version, f"系统参数已回滚到历史取值「{version.get('参数值')}」"
