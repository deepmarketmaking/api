import boto3

def authenticate_user(username, password):
    # Authenticating with Deep MM's AWS Cognito User Pool
    #
    # Note: we use the AWS for authentication and other services,
    # but the websocket connection to the inference servers to our data center
    # located in the NYC metro area (near the equinix data centers where the FINRA TRACE feed originates).

    REGION = 'us-west-2'
    CLIENT_ID = '1hpqr0c8pbiiufsb8n95414jjh'

    cognito_idp = boto3.client('cognito-idp', region_name=REGION)

    cognito_response = cognito_idp.initiate_auth(
        AuthFlow='USER_PASSWORD_AUTH',
        AuthParameters={
            'USERNAME': username,
            'PASSWORD': password,
        },
        ClientId=CLIENT_ID
    )

    if cognito_response['AuthenticationResult']:
        print('ID Token:', cognito_response['AuthenticationResult']['IdToken'])
        print('Access Token:', cognito_response['AuthenticationResult']['AccessToken'])
        print('Refresh Token:', cognito_response['AuthenticationResult']['RefreshToken'])
    else:
        print('Authentication failed')
        exit()

    return cognito_response['AuthenticationResult']['IdToken']