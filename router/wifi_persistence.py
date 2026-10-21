"""Make saved Wi-Fi disable state authoritative over boot-time AP repair."""


def install(namespace):
    original = namespace['enable_radio']

    def enable_radio(radio, vifs):
        # This helper belongs to automatic recovery only. Explicit web/app
        # toggles still use their normal UCI writers and can enable the AP.
        if namespace['get_intents']().get(radio) is False:
            return False
        wireless = namespace['uci_show_dict']('wireless', max_age=0)
        if not wireless or wireless.get(f'wireless.{radio}') != 'wifi-device':
            return False
        if str(wireless.get(f'wireless.{radio}.disabled')) == '1':
            return False
        # Do not let repair re-enable an explicitly disabled AP interface
        # while another interface on this radio is intentionally running.
        if any(str(wireless.get(f'wireless.{vif}.disabled')) == '1' for vif in vifs):
            return False
        return original(radio, vifs)

    namespace['enable_radio'] = enable_radio


def install_wan(namespace):
    # Smart WAN disables its already-disabled STA at each startup. With no
    # relay backup, the vendor fallback interprets any disabled AP as parked
    # by STA, sets radio.disabled=0 and deletes AP.disabled. There is no
    # evidence of a relay transition here: preserve the existing UCI choice.
    # Restoration from a real relay backup remains entirely unchanged.
    def leave_ap_unchanged_without_backup(radio):
        return False

    namespace['_unpark_ap_without_backup'] = leave_ap_unchanged_without_backup
