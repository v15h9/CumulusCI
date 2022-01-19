from logging import getLogger

import requests

from cumulusci.utils.http.requests_utils import safe_json_from_response

from .base import BaseMarketingCloudTask
from .mc_constants import MC_API_VERSION


class GetUserInfoTask(BaseMarketingCloudTask):
    """Retrieves user info of pertaining to the currently logged in user.
    Sanitizes and returns the payload in self.return_values."""

    logger = getLogger(__name__)

    def _run_task(self):
        endpoint = f"https://{self.mc_config.tssd}.auth.marketingcloudapis.com/{MC_API_VERSION}/userinfo"
        headers = {
            "Authorization": f"Bearer {self.mc_config.access_token}",
            "Content-Type": "application/json",
        }
        try:
            response = requests.get(endpoint, headers=headers)
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            self.logger.error(f"Exception occurred fetching user info: {response.text}")
            raise

        self.logger.info("Successfully fetched user info")
        payload = safe_json_from_response(response)
        self.return_values = self._sanitize_payload(payload)

    def _sanitize_payload(self, payload: dict) -> dict:
        """Removes any sensitive or non-pertinent informaiton from the payload.
        This currently includes the following top-level portions of the response:
        (1) rest
        (2) application

        See the following for a comprehensive response example:
        https://developer.salesforce.com/docs/marketing/marketing-cloud/guide/getUserInfo.html
        """
        del payload["rest"]
        del payload["application"]
        return payload
