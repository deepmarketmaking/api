export const connect = (onopen, onmessage) => {
    // Create a WebSocket connection
    const SERVER = 'wss://api.deepmm.com';
    let ws = null;
    let connectionTimeoutTimer = null;
    let openTimeout = 1;
    const makeConnection = () => {
        try {
            ws.close();
        } catch {}
        console.log('Attempting connection to ' + SERVER);
        ws = new WebSocket(SERVER);
        connectionTimeoutTimer = setTimeout(() => {
            openTimeout += 1;
            makeConnection();
        }, openTimeout * 1000);
        ws.onopen = () => {
            if (connectionTimeoutTimer !== null) {
                clearTimeout(connectionTimeoutTimer);
                connectionTimeoutTimer = null;
            }
            console.log('Successful connection to ' + SERVER);
            onopen(ws);
        }
        ws.onmessage = (event) => {
            onmessage(ws, event);
        }
    }
    makeConnection();
};
