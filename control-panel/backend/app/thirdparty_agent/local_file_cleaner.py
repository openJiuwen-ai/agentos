"""Delete local package and image archive files."""

from pathlib import Path

from app.thirdparty_agent.upload_gate import artifact_metadata_path


class LocalFileCleaner:
    def remove_package(self, path: str | None) -> None:
        self._unlink(path)
        if path:
            self._unlink(str(artifact_metadata_path(path)))

    def remove_archive(self, path: str | None) -> None:
        self._unlink(path)

    @staticmethod
    def _unlink(path: str | None) -> None:
        if not path:
            return
        p = Path(path)
        if p.is_file():
            p.unlink(missing_ok=True)
