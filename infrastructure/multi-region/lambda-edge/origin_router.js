/**
 * Lambda@Edge Origin-Request: Dynamic region routing based on ARC routing control.
 *
 * Attached to the /api/* cache behavior on CloudFront. On each origin-request:
 * 1. Checks ARC routing control state (cached for 10s in-memory)
 * 2. Routes to us-east-1 or us-east-2 Agent Proxy API Gateway accordingly
 * 3. Strips the /api prefix from the URI
 *
 * Placeholders replaced at deploy time:
 *   __ARC_ROUTING_CONTROL_ARN__
 *   __ARC_ENDPOINT_*__
 *   __USE1_API_DOMAIN__  (e.g., nplan1hpul.execute-api.us-east-1.amazonaws.com)
 *   __USE2_API_DOMAIN__  (e.g., xyz123.execute-api.us-east-2.amazonaws.com)
 */

'use strict';

const { Route53RecoveryClusterClient, GetRoutingControlStateCommand } = require('@aws-sdk/client-route53-recovery-cluster');

// --- Config (injected at deploy time) ---
const ROUTING_CONTROL_ARN = '__ARC_ROUTING_CONTROL_ARN__';
const ARC_ENDPOINTS = [
    { endpoint: '__ARC_ENDPOINT_USW2__', region: 'us-west-2' },
    { endpoint: '__ARC_ENDPOINT_EUW1__', region: 'eu-west-1' },
    { endpoint: '__ARC_ENDPOINT_APNE1__', region: 'ap-northeast-1' },
    { endpoint: '__ARC_ENDPOINT_APSE2__', region: 'ap-southeast-2' },
    { endpoint: '__ARC_ENDPOINT_USE1__', region: 'us-east-1' },
];

const ORIGINS = {
    'us-east-1': '__USE1_API_DOMAIN__',
    'us-east-2': '__USE2_API_DOMAIN__',
};

// Cache routing control state
let cachedState = 'On';
let cacheExpiry = 0;
const CACHE_TTL_MS = 10000; // 10 seconds

async function getRoutingControlState() {
    const now = Date.now();
    if (now < cacheExpiry) {
        return cachedState;
    }

    for (const ep of ARC_ENDPOINTS) {
        try {
            const client = new Route53RecoveryClusterClient({
                endpoint: ep.endpoint,
                region: ep.region,
            });
            const resp = await client.send(new GetRoutingControlStateCommand({
                RoutingControlArn: ROUTING_CONTROL_ARN,
            }));
            cachedState = resp.RoutingControlState || 'On';
            cacheExpiry = now + CACHE_TTL_MS;
            return cachedState;
        } catch (e) {
            // Try next endpoint
            continue;
        }
    }

    // All endpoints failed — use stale cache
    return cachedState;
}

exports.handler = async (event) => {
    const request = event.Records[0].cf.request;
    const uri = request.uri || '';

    // Only process /api/* requests
    if (!uri.startsWith('/api/')) {
        return request;
    }

    // Determine active region
    const state = await getRoutingControlState();
    // "On" = us-east-1 is active; "Off" = failover to us-east-2
    const activeRegion = (state === 'On') ? 'us-east-1' : 'us-east-2';
    const targetDomain = ORIGINS[activeRegion];

    // Strip /api prefix: /api/invoke → /invoke, /api/oauth2/callback → /oauth2/callback
    request.uri = uri.replace(/^\/api/, '');

    // Switch origin to the active region's API Gateway
    request.origin = {
        custom: {
            domainName: targetDomain,
            port: 443,
            protocol: 'https',
            path: '',
            sslProtocols: ['TLSv1.2'],
            readTimeout: 60,
            keepaliveTimeout: 5,
            customHeaders: {},
        },
    };
    request.headers['host'] = [{ key: 'Host', value: targetDomain }];

    return request;
};
