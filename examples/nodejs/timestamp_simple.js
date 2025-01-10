import { createGetIdToken } from "./authentication.js";

const args = process.argv.slice(2);
if (args.length != 4) {
    throw new Error('Usage: python timestamp_simple.py <AWS Region> <Cognito Client ID> <Deep MM dev username> <password>\nSee README for additional details');
}
const getIdToken = createGetIdToken(args[0], args[1], args[2], args[3]);

// subscription message
const msg = {
    inference: [
        {
            rfq_label: 'spread',
            figi: 'BBG00M53S4K8',
            quantity: 1000000,
            side: 'bid',
            ats_indicator: "N",
            timestamp: ['2024-12-09T18:31:45.477Z', '2024-12-08T18:04:45.477Z']
        }, // add additional inference requests here (up to the throttling limits)
    ]
}

const ws = new WebSocket('wss://staging1.deepmm.com'); // Replace with your server URL

ws.onopen = () => {
    // get an id token, then send our message with the token
    getIdToken().then(token => void ws.send(JSON.stringify({...msg, token})));
};

ws.onmessage = (event) => {
    console.log(JSON.stringify(JSON.parse(event['data']), null, 2));
    // close the WebSocket when we have received all the data
    ws.close();
};
