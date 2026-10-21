"""FM350 telemetry correction for the stock web service; never writes AT settings.

The LCD consumes dashboard.modem_signal_strength. Use measured RSRP rather
than CSQ for LTE/NR, preferring NR only when its current report is valid.
"""
import re
import time

MAX_AGE = 150


def text(response):
    return response.decode('utf-8', errors='replace') if isinstance(response, bytes) else response


def indexed(value, maximum, base, step=1):
    # Report the lower edge of the quantization interval. 0 is below range.
    if not 0 <= value <= maximum:
        return None
    return base + (value - 1) * step


def parse_cesq(response):
    match = re.search(r'^\+CESQ:\s*([\d, ]+)', text(response), re.M)
    if not match:
        return None
    try:
        v = [int(x.strip()) for x in match[1].split(',')]
        if len(v) < 6:
            return None
        lte = dict(rsrp=indexed(v[5], 97, -140), rsrq=indexed(v[4], 34, -19.5, .5))
        nr = dict(rsrp=None, rsrq=None, sinr=None)
        # Observed FM350 idle sentinel: all three NR fields become zero while
        # LTE and recent NR carrier reports remain valid. Do not invent -157 dBm.
        nr_unreported = len(v) >= 9 and v[6:9] == [0, 0, 0]
        if len(v) >= 9 and not nr_unreported:
            nr = dict(rsrp=indexed(v[7], 126, -156),
                      rsrq=indexed(v[6], 126, -43, .5),
                      sinr=indexed(v[8], 127, -23, .5))
        return {'lte': lte, 'nr': nr, 'nr_unreported': nr_unreported}
    except ValueError:
        return None


def band_name(code):
    if 101 <= code <= 171:
        return 'LTE', 'B' + str(code - 100)
    if str(code).startswith('50'):
        # Firmware uses both 501 and 5001 for NR n1.
        n = int(str(code)[2:])
        if 1 <= n <= 512:
            return 'NR', 'n' + str(n)
    raise ValueError('Unsupported band')


def parse_ca(response):
    result = []
    for line in text(response).splitlines():
        match = re.match(r'\s*(PCC|SCC\s*\d+):\s*(.*)', line)
        if not match:
            continue
        try:
            v = [int(x.strip()) for x in match[2].split(',')]
            primary = match[1] == 'PCC'
            if primary and len(v) not in (9, 10) or not primary and len(v) != 12:
                continue
            offset = 0 if primary else 2
            rat, band = band_name(v[offset])
            bw = v[offset + 3]
            width = {6: 1.4, 15: 3, 25: 5, 50: 10, 75: 15, 100: 20}.get(bw) if rat == 'LTE' else bw / 5
            mimo_index = (5 if len(v) == 10 else 4) if primary else 7
            result.append(dict(role=match[1].replace(' ', ''), rat=rat, band=band,
                               bandwidth_mhz=width, active=primary or v[0] == 2,
                               dl_layers=v[mimo_index], rsrp=v[-1]))
        except (ValueError, IndexError):
            continue
    return result


def signal_percent(rsrp):
    if rsrp is None:
        return None
    # Four explicit strength levels; 0 below -110 dBm. Quality stays separate.
    return sum(rsrp >= threshold for threshold in (-110, -100, -90, -80)) * 25


def snapshot(client, now=None):
    now = time.monotonic() if now is None else now
    record = getattr(client, '_pc_radio_signal', None)
    if record is None or now - record[0] > MAX_AGE:
        return None
    signal = record[1]
    nr = signal['nr']['rsrp'] is not None
    lte = signal['lte']['rsrp'] is not None
    selected = signal['nr'] if nr else signal['lte']
    ca_record = getattr(client, '_pc_radio_ca', None)
    carriers = ca_record[1] if ca_record and now - ca_record[0] <= MAX_AGE else []
    # A fresh LTE-only measurement must not keep old NR carriers on screen.
    carriers = [x for x in carriers if nr or signal.get('nr_unreported') or x['rat'] != 'NR']
    nr_present = nr or (signal.get('nr_unreported', False) and any(
        x['rat'] == 'NR' and x['active'] for x in carriers))
    return dict(mode='5G NSA' if nr_present and lte else '5G' if nr_present else 'LTE' if lte else None,
                rsrp=selected['rsrp'], rsrq=selected['rsrq'], sinr=selected.get('sinr'),
                signal_percent=signal_percent(selected['rsrp']),
                signal_source='NR SS-RSRP' if nr else 'LTE RSRP',
                age_seconds=round(now - record[0], 1), carriers=carriers,
                lte=signal['lte'], nr=signal['nr'])


def install(namespace):
    """Patch only FM350 results; retain original routes, auth, threads and I/O."""
    # Routes are imported before the stock bootstrap creates the modem client.
    from pc_modem_client import PcModemClient
    flask_app = namespace['flask_app']
    cls = PcModemClient
    if getattr(cls, '_pc_radio_patch', False):
        return
    cls._pc_radio_patch = True
    original_cesq = cls.handle_cesq
    original_ca = cls.handle_gtcainfo

    def cesq(self, response):
        original_cesq(self, response)
        if self.is_fm350():
            parsed = parse_cesq(response)
            if parsed is not None:
                self._pc_radio_signal = (time.monotonic(), parsed)

    def ca(self, response):
        original_ca(self, response)
        if self.is_fm350() and '+GTCAINFO:' in text(response):
            self._pc_radio_ca = (time.monotonic(), parse_ca(response))

    cls.handle_cesq = cesq
    cls.handle_gtcainfo = ca
    original_dashboard = namespace['get_dashboard_data']

    def dashboard(*args, **kwargs):
        data = original_dashboard(*args, **kwargs)
        client = namespace['pc_app'].modem_client
        if client is None or not client.is_fm350():
            return data
        data = dict(data)
        radio = snapshot(client)
        # Do not show cached strong bars when the SIM is absent or powered off.
        connected = data.get('sim_state') == 'ready' and data.get('wwan_powered', True)
        data['modem_signal_strength'] = (radio.get('signal_percent') or 0) if radio and connected else 0
        data['modem_radio'] = radio if connected else None
        return data

    namespace['get_dashboard_data'] = dashboard
    from flask import request

    @flask_app.after_request
    def radio_response(response):
        client = namespace['pc_app'].modem_client
        if request.path != '/api/v1/modem/basic.json' or response.status_code != 200 or client is None or not client.is_fm350():
            return response
        data = response.get_json(silent=True)
        radio = snapshot(client)
        if not isinstance(data, dict) or not radio:
            return response
        data['radio'] = radio
        if radio['mode']:
            data['modem_network_info'] = radio['mode']
            fields = [radio.get('sinr'), radio.get('rsrq'), radio.get('rsrp')]
            data['modem_serving_quality'] = ', '.join(
                '—' if v is None else f'{v:g} {unit}'
                for v, unit in zip(fields, ('dB', 'dB', 'dBm')))
            data['modem_cell_signal_details'] = data['modem_serving_quality']
        carriers = [x for x in radio['carriers'] if x['active']]
        if carriers:
            data['cell_carrier_info'] = ' + '.join(
                f"{x['band']} ({x['bandwidth_mhz']:g} MHz)" if x['bandwidth_mhz'] is not None else x['band']
                for x in carriers)
        # json.dumps through Flask preserves its configured serialization.
        response.set_data(flask_app.json.dumps(data))
        return response
