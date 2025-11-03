import base64
import json
import time
from typing import Callable

import boto3


def create_get_id_token(region: str, client_id: str, username: str, password: str) -> Callable[[],str] :
    # Call this with the appropriate region, client_id, username, and password.
    # Returns a function that will return a valid token when it is called.
    # Usage example:
    #     get_id_token = create_get_id_token(...)
    #     msg = { 'token': get_id_token(), ... }
    #     websocket.send(json.dumps(msg))
    cognito_idp = boto3.client('cognito-idp', region_name=region)
    refresh_token = None
    id_token = None
    auth_time = None
    exp = None
    def _user_password_auth():
        nonlocal refresh_token, id_token
        response = cognito_idp.initiate_auth(
            AuthFlow='USER_PASSWORD_AUTH',
            AuthParameters={'USERNAME': username, 'PASSWORD': password},
            ClientId=client_id)
        refresh_token = response['AuthenticationResult']['RefreshToken']
        id_token = response['AuthenticationResult']['IdToken']
        _extract_id_token_claims()
    def _refresh_token_auth():
        nonlocal id_token
        response = cognito_idp.initiate_auth(
            AuthFlow='REFRESH_TOKEN_AUTH',
            AuthParameters={'REFRESH_TOKEN': refresh_token},
            ClientId=client_id)
        id_token = response['AuthenticationResult']['IdToken']
        _extract_id_token_claims()
    def _extract_id_token_claims():
        nonlocal auth_time, exp
        claims_payload = id_token.split(".")[1]
        claims_string = str(base64.b64decode(claims_payload + "=="), "utf-8")
        claims = json.loads(claims_string)
        auth_time = claims['auth_time']
        exp = claims['exp']
    def _get_id_token():
        if id_token is None or time.time() - auth_time > 3600:
            _user_password_auth()
        elif exp - time.time() < 120:
            _refresh_token_auth()
        return id_token
    return _get_id_token
