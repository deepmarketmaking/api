export const connect = (onopen, onmessage) => {
    // Create a WebSocket connection
    const SERVER_LIST = ['wss://deist.deepmm.com', 'wss://hayek.deepmm.com'];
    let serverIndex = Math.floor(Math.random() * SERVER_LIST.length);
    let ws = null;
    let connectionTimeoutTimer = null;
    let openTimeout = 1;
    const makeConnection = () => {
        try {
            ws.close();
        } catch {}
        console.log('Attempting connection to ' + SERVER_LIST[serverIndex]);
        ws = new WebSocket(SERVER_LIST[serverIndex]);
        connectionTimeoutTimer = setTimeout(() => {
            serverIndex = serverIndex == SERVER_LIST.length - 1 ? 0 : serverIndex + 1;
            openTimeout += 1;
            makeConnection();
        }, openTimeout * 1000);
        ws.onopen = () => {
            if (connectionTimeoutTimer !== null) {
                clearTimeout(connectionTimeoutTimer);
                connectionTimeoutTimer = null;
            }
            console.log('Successful connection to ' + SERVER_LIST[serverIndex]);
            onopen(ws);
        }
        ws.onmessage = (event) => {
            onmessage(ws, event);
        }
    }
    makeConnection();
};
