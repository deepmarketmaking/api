from collections.abc import Iterable
import time

import httpx
from tenacity import Retrying, stop_after_delay, wait_fixed, wait_random

import pyarrow as pa

# HEAVILY MODIFIED DERIVATIVE OF THE CODE FOUND HERE:
# https://github.com/OpenFIGI/api-examples/blob/master/python/example-with-requests.py

# Copyright 2017 Bloomberg Finance L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# HEAVILY MODIFIED DERIVATIVE OF THE CODE FOUND HERE:
# https://github.com/OpenFIGI/api-examples/blob/master/python/example-with-requests.py

# Copyright 2017 Bloomberg Finance L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


def openfigi_map_cusips_to_figis(api_key, cusip_list):
    _openfigi_cache_column_types: dict[str, pa.DataType] = {
        'cusip': pa.string(),
        'figi': pa.string(),
        'name': pa.string(),
        'ticker': pa.string(),
        'exchCode': pa.string(),
        'compositeFIGI': pa.string(),
        'securityType': pa.string(),
        'marketSector': pa.string(),
        'shareClassFIGI': pa.string(),
        'securityType2': pa.string(),
        'securityDescription': pa.string()}

    global _MAX_JOBS_PER_REQUEST, _MIN_REQUEST_INTERVAL, c, result, cusip_to_figi, figi_to_cusip
    _MAX_JOBS_PER_REQUEST = 90  # official limit: 100
    _MIN_REQUEST_INTERVAL = 0.5  # official limit: 25 per 6 seconds
    _last_response_time_dict = {'last_response_time': 0}
    # OpenFIGI is sometimes flaky so we have a very forgiving retry policy.
    # We also don't want to run forever waiting for OpenFIGI.
    # This sets the maximum runtime during which we allow retries
    # for failed OpenFIGI requests.
    _MAX_RETRY_RUNTIME = 1800
    retry_stop_time = time.time() + _MAX_RETRY_RUNTIME

    def _map_jobs(jobs: Iterable[dict], retry_stop_time: float):
        '''
        Generator that yields (job, result) tuples.  Takes care of batching and throttling.

        Parameters
        ----------
        jobs : iter(dict)
            An iterable of dicts that conform to the OpenFIGI API request structure. See
            https://www.openfigi.com/api#request-format for more information.

        Yields
        -------
        (dict, dict)
            First dict is the job, second dict is the result conforming to the OpenFIGI API
            response structure.  See https://www.openfigi.com/api#response-fomats
            for more information.
        '''
        url = 'https://api.openfigi.com/v3/mapping'
        headers = {'Content-Type': 'text/json', 'X-OPENFIGI-APIKEY': api_key}
        batch = []

        def process_batch():
            if batch:
                # sleep when needed to stay under the API rate limit
                interval = time.time() - _last_response_time_dict['last_response_time']
                if interval < _MIN_REQUEST_INTERVAL:
                    time.sleep(_MIN_REQUEST_INTERVAL - interval)
                for attempt in Retrying(
                        stop=stop_after_delay(max(0, retry_stop_time - time.time())),
                        # allow retries while retry time remains
                        wait=wait_fixed(6) + wait_random(0, 4)):  # wait 6-10s between attempts
                    with attempt:
                        response = httpx.post(url=url, headers=headers, json=batch, timeout=30)
                        if response.status_code != httpx.codes.OK:
                            print(f'OpenFIGI status_code not OK: {response.status_code}')
                            raise Exception(f'OpenFIGI status_code not OK: {response.status_code}')
                _last_response_time_dict['last_response_time'] = time.time()
                results = response.json()
                for job, result in zip(batch, results):
                    yield (job, result)
            batch.clear()

        for job in jobs:
            batch.append(job)
            if len(batch) >= _MAX_JOBS_PER_REQUEST:
                for pair in process_batch():
                    yield pair
        for pair in process_batch():
            yield pair

    # ---------- END DERIVATIVE CODE ----------

    print("Mapping list of CUSIPs to FIGIs using OpenFIGI API")

    # NOTE: !! ID_CUSIP is one of at least two relevant ID types for CUSIPs.  The other is ID_CINS. This is just an example.
    open_figi_data = {c: [] for c in _openfigi_cache_column_types}
    for i, (job, result) in enumerate(
            _map_jobs(({"idType": "ID_CUSIP", "idValue": c} for c in cusip_list), retry_stop_time)):
        if 'warning' in result:
            print(f'''OpenFigi warning for request "{job}": "{result['warning']}"''')
        if 'data' in result:
            if len(result['data']) != 1:
                print(f'''OpenFigi unexpected response for request "{job}": "{result['data']}"''')
            else:
                for c in (c for c in _openfigi_cache_column_types if c != 'cusip'):
                    open_figi_data[c].append(result['data'][0][c] if c in result['data'][0] else '')
                open_figi_data['cusip'].append(job['idValue'])
    print(open_figi_data)
    # Create a dictionary mapping the CUSIPs to the FIGIs
    cusip_to_figi = dict(zip(open_figi_data['cusip'], open_figi_data['figi']))
    figi_to_cusip = dict(zip(open_figi_data['figi'], open_figi_data['cusip']))

    return cusip_to_figi, figi_to_cusip