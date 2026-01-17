import { CognitoIdentityProviderClient, InitiateAuthCommand } from '@aws-sdk/client-cognito-identity-provider';

export const createGetIdToken = (region, clientId, username, password) => {
    const client = new CognitoIdentityProviderClient({ region });
    let refreshToken = null;
    let idToken = null;
    let authTime = null;
    let exp = null;
    const userPasswordAuth = async () => {
        const command = new InitiateAuthCommand({
            AuthFlow: 'USER_PASSWORD_AUTH',
            AuthParameters: {'USERNAME': username, 'PASSWORD': password},
            ClientId: clientId
        });
        const response = await client.send(command);
        refreshToken = response['AuthenticationResult']['RefreshToken'];
        idToken = response['AuthenticationResult']['IdToken'];
        extractIdTokenClaims();
    };
    const refreshTokenAuth = async () => {
        const command = new InitiateAuthCommand({
            AuthFlow: 'REFRESH_TOKEN_AUTH',
            AuthParameters: {'REFRESH_TOKEN': refreshToken},
            ClientId: clientId
        });
        const response = await client.send(command);
        idToken = response['AuthenticationResult']['IdToken'];
        extractIdTokenClaims();
    }
    const extractIdTokenClaims = () => {
        const claimsPayload = idToken.split('.')[1];
        const claimsString = Buffer.from(claimsPayload + '==', 'base64').toString('ascii');
        const claims = JSON.parse(claimsString);
        authTime = claims['auth_time'];
        exp = claims['exp'];
    };
    const getIdToken = async () => {
        if (!idToken || (Date.now() / 1000) - authTime > 3600) {
            await userPasswordAuth();
        } else if (exp - (Date.now() / 1000) < 120) {
            await refreshTokenAuth();
        }
        return idToken;
    }
    return getIdToken;
}

