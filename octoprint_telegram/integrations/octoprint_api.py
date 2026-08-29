from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable
from urllib.parse import urljoin

import requests

if TYPE_CHECKING:
    from ..core.settings import OctoPrintSettings

TEXTUAL_CONTENT_TYPES = [
    "application/json",
    "text/plain",
    "text/html",
    "text/xml",
    "application/xml",
    "text/javascript",
    "application/javascript",
]

MAX_LOGGED_RESPONSE_BYTES = 10 * 1024


class OctoPrintApi:
    """The OctoPrint HTTP API."""

    def __init__(
        self,
        server_port: int,
        generate_plugin_api_key: Callable[[], str | None],
        octoprint_settings: OctoPrintSettings,
        logger: logging.Logger,
    ) -> None:
        """Set up the HTTP API client against a running OctoPrint server.

        Args:
            server_port (int): The port OctoPrint's API is served on.
            generate_plugin_api_key (Callable): Callback that returns a fresh plugin API key, valid for a
                single request, or None when OctoPrint provides none.
            octoprint_settings (OctoPrintSettings): The settings stored by OctoPrint itself.
            logger (logging.Logger): The logger to write to.
        """
        self._server_port = server_port
        self._generate_plugin_api_key = generate_plugin_api_key
        self._octoprint_settings = octoprint_settings
        self._logger = logger.getChild("OctoPrintApi")

    def send_simpleapi_command(
        self, plugin_id: str, command: str, parameters: dict | None = None, timeout: int = 5
    ) -> requests.Response:
        """Send a SimpleAPI command to an OctoPrint plugin via the HTTP API.

        Args:
            plugin_id (str): The ID of the plugin to target.
            command (str): The command string to send to the plugin.
            parameters (dict, optional): Additional parameters to include in the request body.
            timeout (int, optional): Timeout for the request in seconds. Defaults to 5.

        Returns:
            requests.Response: The response object from the POST request.

        Raises:
            requests.HTTPError: If the response contains an HTTP error status code.
        """
        payload = {"command": command}
        if parameters:
            payload.update(parameters)

        return self.send_request(
            f"/api/plugin/{plugin_id}",
            "POST",
            headers={
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )

    def send_simpleapi_get(self, plugin_id: str, parameters: dict | None = None, timeout: int = 5) -> requests.Response:
        """Send a SimpleAPI GET request to an OctoPrint plugin via the HTTP API.

        Args:
            plugin_id (str): The ID of the plugin to target.
            parameters (dict, optional): Query parameters to include in the request.
            timeout (int, optional): Timeout for the request in seconds. Defaults to 5.

        Returns:
            requests.Response: The response object from the GET request.

        Raises:
            requests.HTTPError: If the response contains an HTTP error status code.
        """
        return self.send_request(
            f"/api/plugin/{plugin_id}",
            params=parameters or {},
            timeout=timeout,
        )

    def send_request(self, url: str, method: str = "GET", **kwargs: Any) -> requests.Response:
        """Send an HTTP request to the OctoPrint API with default authentication headers.

        Args:
            url (str): Full or relative URL (e.g., "/api/plugin/...").
            method (str): The HTTP method to use (e.g., "GET", "POST", "PUT", "PATCH", "DELETE", ...). Defaults to "GET".
            **kwargs: Additional arguments passed to the underlying requests library (e.g., 'data', 'params', 'files').

        Returns:
            requests.Response: The response object from the HTTP request.

        Raises:
            requests.HTTPError: If the response contains an HTTP error status code.
        """
        url = urljoin(f"http://localhost:{self._server_port}/", url)

        method = method.lower()

        api_key = self._generate_plugin_api_key()
        if api_key is None:  # Fallback for OctoPrint versions < 1.12.0
            api_key = self._octoprint_settings.global_api_key
            if not api_key:
                self._logger.error(
                    "Global API Key not enabled. Most integrations with third-party plugins require enabling the Global API Key in OctoPrint Settings -> API -> Global API Key."
                )

        default_headers = {
            "X-Api-Key": api_key,
        }
        headers = {**default_headers, **(kwargs.get("headers") or {})}
        kwargs.pop("headers", None)

        default_kwargs = {
            "headers": headers,
            "timeout": 5,
        }
        request_kwargs: dict[str, Any] = {**default_kwargs, **kwargs}

        loggable_kwargs = {}
        for k, v in request_kwargs.items():
            if k == "headers":
                loggable_kwargs[k] = {**headers, "X-Api-Key": "REDACTED"}
            elif k == "files":
                loggable_kwargs[k] = "<binary data>"
            else:
                loggable_kwargs[k] = v
        self._logger.debug("Sending OctoPrint request: method=%s, url=%s, kwargs=%s", method, url, loggable_kwargs)

        response = requests.request(method, url, **request_kwargs)

        # Check if response content should be logged
        content_type = response.headers.get("content-type", "").lower()
        content_length = len(response.content)
        is_textual = any(ct in content_type for ct in TEXTUAL_CONTENT_TYPES)
        is_reasonable_size = content_length < MAX_LOGGED_RESPONSE_BYTES
        if is_textual and is_reasonable_size:
            self._logger.debug("Received OctoPrint response: status=%s, text=%s", response.status_code, response.text)
        else:
            self._logger.debug(
                "Received OctoPrint response: status=%s, content-type=%s, size=%s bytes",
                response.status_code,
                content_type,
                content_length,
            )

        response.raise_for_status()
        return response
