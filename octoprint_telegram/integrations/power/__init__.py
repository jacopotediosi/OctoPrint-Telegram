from __future__ import annotations

from .base import PowerPlugin
from .domoticz import DomoticzPowerPlugin
from .enclosure import EnclosurePowerPlugin
from .gpiocontrol import GpioControlPowerPlugin
from .ikea_tradfri import IkeaTradfriPowerPlugin
from .mystromswitch import MyStromSwitchPowerPlugin
from .octohue import OctoHuePowerPlugin
from .octolight import OctoLightPowerPlugin
from .octolight_ha import OctoLightHAPowerPlugin
from .octorelay import OctoRelayPowerPlugin
from .orvibos20 import OrviboS20PowerPlugin
from .psucontrol import PSUControlPowerPlugin
from .tasmota import TasmotaPowerPlugin
from .tasmota_mqtt import TasmotaMQTTPowerPlugin
from .tplinksmartplug import TPLinkSmartplugPowerPlugin
from .tuyasmartplug import TuyaSmartplugPowerPlugin
from .usbrelaycontrol import USBRelayControlPowerPlugin
from .wemoswitch import WemoSwitchPowerPlugin
from .wled import WledPowerPlugin
from .ws281x import WS281xPowerPlugin
from .wyze import WyzePowerPlugin

POWER_PLUGINS: tuple[type[PowerPlugin], ...] = (
    DomoticzPowerPlugin,
    EnclosurePowerPlugin,
    GpioControlPowerPlugin,
    IkeaTradfriPowerPlugin,
    MyStromSwitchPowerPlugin,
    OctoHuePowerPlugin,
    OctoLightPowerPlugin,
    OctoLightHAPowerPlugin,
    OctoRelayPowerPlugin,
    OrviboS20PowerPlugin,
    PSUControlPowerPlugin,
    TasmotaPowerPlugin,
    TasmotaMQTTPowerPlugin,
    TPLinkSmartplugPowerPlugin,
    TuyaSmartplugPowerPlugin,
    USBRelayControlPowerPlugin,
    WemoSwitchPowerPlugin,
    WledPowerPlugin,
    WS281xPowerPlugin,
    WyzePowerPlugin,
)

__all__ = ["POWER_PLUGINS", "PowerPlugin"]
