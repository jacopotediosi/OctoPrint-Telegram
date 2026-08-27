from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import octoprint.plugin

if TYPE_CHECKING:
    from ..core.settings import OctoPrintSettings
    from ..integrations.plugins import Plugins


class WebcamProfile:
    def __init__(
        self,
        name: str | None = None,
        snapshot: str | None = None,
        snapshotTimeout: int | None = 15,
        snapshotSslValidation: bool = True,
        stream: str | None = None,
        flipH: bool = False,
        flipV: bool = False,
        rotate90: bool = False,
        provider: octoprint.plugin.types.WebcamProviderPlugin | None = None,
    ):
        self.name = name
        self.snapshot = snapshot
        self.snapshotTimeout = snapshotTimeout
        self.snapshotSslValidation = snapshotSslValidation
        self.stream = stream
        self.flipH = flipH
        self.flipV = flipV
        self.rotate90 = rotate90
        self.provider = provider

    def __repr__(self):
        return (
            f"<WebcamProfile name={self.name!r} snapshot={self.snapshot!r} "
            f"snapshotTimeout={self.snapshotTimeout!r} snapshotSslValidation={self.snapshotSslValidation} "
            f"stream={self.stream!r} flipH={self.flipH} flipV={self.flipV} rotate90={self.rotate90} "
            f"provider={type(self.provider).__name__ if self.provider is not None else None}>"
        )


class Webcams:
    """The webcams OctoPrint knows about."""

    def __init__(self, plugin_manager, plugins: Plugins, octoprint_settings: OctoPrintSettings, logger: logging.Logger):
        self._plugin_manager = plugin_manager
        self._plugins = plugins
        self._octoprint_settings = octoprint_settings
        self._logger = logger.getChild("Webcams")

    def get_webcam_profiles(self) -> list[WebcamProfile]:
        webcam_profiles: list[WebcamProfile] = []

        # New webcam integration (OctoPrint >= 1.9.0)
        try:
            from octoprint.webcams import get_webcams
        except ImportError:
            get_webcams = None
            self._logger.debug("New webcam integration not available, this OctoPrint is older than 1.9.0")

        if get_webcams:
            try:
                self._logger.debug("Getting webcam profiles from new webcam integration")

                for provided_webcam in get_webcams(plugin_manager=self._plugin_manager).values():
                    wc = provided_webcam.config

                    can_snapshot = bool(getattr(wc, "canSnapshot", False))

                    compat = getattr(wc, "compat", None)
                    if not compat and not can_snapshot:
                        self._logger.debug(
                            "Skipped webcam %s, it can't take snapshots and has no compatibility layer",
                            getattr(wc, "name", None),
                        )
                        continue

                    webcam_profile = WebcamProfile(
                        name=getattr(wc, "name", None),
                        snapshot=getattr(compat, "snapshot", None),
                        snapshotTimeout=max(15, getattr(compat, "snapshotTimeout", 0) or 0),
                        snapshotSslValidation=bool(getattr(compat, "snapshotSslValidation", True)),
                        stream=getattr(compat, "stream", None),
                        flipH=bool(getattr(wc, "flipH", False)),
                        flipV=bool(getattr(wc, "flipV", False)),
                        rotate90=bool(getattr(wc, "rotate90", False)),
                        provider=getattr(provided_webcam, "providerPlugin", None) if can_snapshot else None,
                    )

                    webcam_profiles.append(webcam_profile)
            except Exception:
                self._logger.exception("Caught exception getting new webcam integration profiles")

        # Fallback to Multicam plugin
        if not webcam_profiles:
            self._logger.warning("No webcams found via the new integration, falling back to Multicam plugin")

            try:
                if self._plugins.is_enabled("multicam"):
                    multicam_profiles = self._octoprint_settings.plugin_setting("multicam", "multicam_profiles") or []
                    self._logger.debug("Multicam profiles: %s", multicam_profiles)

                    for multicam_profile in multicam_profiles:
                        webcam_profile = WebcamProfile(
                            name=multicam_profile.get("name"),
                            snapshot=multicam_profile.get("snapshot"),
                            snapshotTimeout=15,  # Multicam currently doesn't expose snapshotTimeout, see https://github.com/mikedmor/OctoPrint_MultiCam/issues/78
                            snapshotSslValidation=False,  # Multicam doesn't expose snapshotSslValidation either
                            stream=multicam_profile.get("URL"),
                            flipH=bool(multicam_profile.get("flipH", False)),
                            flipV=bool(multicam_profile.get("flipV", False)),
                            rotate90=bool(multicam_profile.get("rotate90", False)),
                        )
                        webcam_profiles.append(webcam_profile)
                else:
                    self._logger.warning("Multicam not installed or disabled")
            except Exception:
                self._logger.exception("Caught exception getting Multicam profiles")

        # Fallback to legacy webcam settings
        if not webcam_profiles:
            self._logger.warning("No webcams found via Multicam, falling back to legacy webcam settings")

            try:
                webcam_profile = WebcamProfile(
                    name=self._octoprint_settings.webcam_name,
                    snapshot=self._octoprint_settings.webcam_snapshot,
                    snapshotTimeout=max(15, self._octoprint_settings.webcam_snapshot_timeout or 0),
                    snapshotSslValidation=self._octoprint_settings.webcam_snapshot_ssl_validation,
                    stream=self._octoprint_settings.webcam_stream,
                    flipH=self._octoprint_settings.webcam_flip_h,
                    flipV=self._octoprint_settings.webcam_flip_v,
                    rotate90=self._octoprint_settings.webcam_rotate_90,
                )
                webcam_profiles.append(webcam_profile)
            except Exception:
                self._logger.exception("Caught exception getting legacy webcam settings")

        self._logger.debug("Final webcam profiles: %s", webcam_profiles)

        return webcam_profiles
