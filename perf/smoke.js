import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '30s', target: 10 },
    { duration: '1m', target: 20 },
    { duration: '30s', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<600'],
  },
};

const baseUrl = (__ENV.BASE_URL || 'https://staging.scholarship.example.com').replace(/\/?$/, '');
const healthEndpoint = '/api/v1/health';

export default function () {
  const response = http.get(`${baseUrl}${healthEndpoint}`);
  check(response, {
    'status is 200': (r) => r.status === 200,
  });
  sleep(1);
}
