import { createGetIdToken } from "./authentication.js";
import { connect } from "./connection.js";

const args = process.argv.slice(2);
if (args.length != 4) {
    throw new Error('Usage: python subscribe_simple.py <AWS Region> <Cognito Client ID> <Deep MM dev username> <password>\nSee README for additional details');
}
const getIdToken = createGetIdToken(args[0], args[1], args[2], args[3]);

// subscription message
const msg = {
    inference: [
        {
            rfq_label: 'spread',
            figi: 'BBG00K85WG22',
            quantity: 1000000,
            side: 'bid',
            ats_indicator: 'N',
            subscribe: true
        }, // add additional inference requests here (up to the throttling limits)
    ]
}

const onopen = (ws) => {
    // get an id token, then send our message with the token
    getIdToken().then(token => void ws.send(JSON.stringify({...msg, token})));
    // periodically send an updated token to the server so the session does not expire
    // NOTE: the server does send a response to a message with only an updated token
    setInterval(() => void getIdToken().then(token => void ws.send(JSON.stringify({ token }))), 60 * 1000)
};

const onmessage = (ws, event) => {
    console.log(JSON.stringify(JSON.parse(event['data']), null, 2));
};

connect(onopen, onmessage);
