"""Persistence layer for fit-once sklearn models.

Each model is stored as two files inside *models_dir*:
  <model_id>.joblib        — serialised sklearn object (via joblib)
  <model_id>.meta.json     — lightweight metadata dict

This module intentionally imports nothing from ``lutz.analytics`` to avoid
circular imports.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class FittedModelStore:
    """Persist and load fitted sklearn models to/from a local directory.

    Parameters
    ----------
    models_dir:
        Directory where ``.joblib`` and ``.meta.json`` files are stored.
        The directory is created if it does not exist.
    """

    def __init__(self, models_dir: Path) -> None:
        self._dir = Path(models_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Internal paths
    # ------------------------------------------------------------------

    def _joblib_path(self, model_id: str) -> Path:
        return self._dir / f"{model_id}.joblib"

    def _meta_path(self, model_id: str) -> Path:
        return self._dir / f"{model_id}.meta.json"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(self, model_id: str, model: object, metadata: dict) -> None:
        """Serialise *model* and write *metadata* to disk.

        Parameters
        ----------
        model_id:
            Unique identifier (e.g. ``"kmeans_8"``).
        model:
            Any sklearn-compatible estimator (must support ``joblib.dump``).
        metadata:
            Arbitrary dict — will be round-tripped via JSON.
        """
        import joblib

        joblib.dump(model, self._joblib_path(model_id))
        self._meta_path(model_id).write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.debug("Saved model '%s' to %s", model_id, self._dir)

    def load(self, model_id: str) -> tuple[object, dict]:
        """Load and return ``(model, metadata)`` for *model_id*.

        Raises
        ------
        FileNotFoundError
            If the model has not been saved yet.
        """
        import joblib

        joblib_path = self._joblib_path(model_id)
        meta_path = self._meta_path(model_id)

        if not joblib_path.exists():
            raise FileNotFoundError(
                f"Model '{model_id}' not found in {self._dir} — "
                f"run 'lutz model fit' to train it first."
            )

        model = joblib.load(joblib_path)
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        logger.debug("Loaded model '%s' from %s", model_id, self._dir)
        return model, metadata

    def list_models(self) -> list[dict]:
        """Return a list of metadata dicts for every saved model."""
        result = []
        for meta_file in sorted(self._dir.glob("*.meta.json")):
            try:
                metadata = json.loads(meta_file.read_text(encoding="utf-8"))
                result.append(metadata)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Skipping malformed metadata file %s: %s", meta_file, exc)
        return result

    def remove(self, model_id: str) -> None:
        """Delete both artefact files for *model_id*.

        No-op if the model does not exist.
        """
        for path in (self._joblib_path(model_id), self._meta_path(model_id)):
            if path.exists():
                path.unlink()
        logger.debug("Removed model '%s'", model_id)

    def exists(self, model_id: str) -> bool:
        """Return True if both artefact files are present on disk."""
        return self._joblib_path(model_id).exists() and self._meta_path(model_id).exists()

    def check_corpus_valid(self, model_id: str, current_hash: str) -> bool:
        """Return True if the stored model's corpus_hash matches *current_hash*.

        Emits a warning (logger.warning) when the corpus has changed since the
        model was trained, so the researcher is informed without raising an
        exception.

        Returns False (and logs a warning) when the hashes diverge.
        """
        if not self.exists(model_id):
            return False

        try:
            meta_path = self._meta_path(model_id)
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False

        saved_hash = metadata.get("corpus_hash", "")
        if saved_hash != current_hash:
            logger.warning(
                "Model '%s' was trained on corpus_hash=%r but current corpus_hash=%r. "
                "Re-run 'lutz model fit' to retrain on the updated corpus.",
                model_id,
                saved_hash,
                current_hash,
            )
            return False
        return True
