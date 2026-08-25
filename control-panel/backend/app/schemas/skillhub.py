"""Pydantic 请求/响应模型 — SkillHub skill 安装。"""

from pydantic import BaseModel, Field


class InstallSkillRequest(BaseModel):
    """安装 skill 请求体。"""

    skill_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        # F-5: asset_id 固定 32 位小写 hex（SkillHub 接口参考 GET /plugins items[].asset_id），
        # 用 pattern 精确收紧，杜绝 skill_id 直接拼进 URL 时的路径穿越/注入
        pattern=r"^[a-f0-9]{32}$",
        description="SkillHub 公开 skill 的 asset_id（来自 GET /plugins 的 items[].asset_id，32 位小写 hex）",
    )
    version: str | None = Field(None, description="版本号（x.y.z）；缺省安装最新公开版本")
    force: bool = Field(True, description="同名已存在时是否覆盖重装；false 则返回 409")


class InstalledSkill(BaseModel):
    """安装结果。"""

    name: str
    version: str
    install_path: str
    installed_at: str
