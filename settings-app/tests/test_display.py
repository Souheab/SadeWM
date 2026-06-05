from sadesettings.display import parse_xrandr_query


SAMPLE = """Screen 0: minimum 8 x 8, current 1920 x 1080, maximum 32767 x 32767
HDMI-1 connected primary 1920x1080+0+0 (normal left inverted right x axis y axis) 510mm x 290mm
   1920x1080     60.00*+  59.94    50.00
   1280x720      60.00    59.94
DP-1 disconnected (normal left inverted right x axis y axis)
"""


def test_parse_xrandr_query_connected_output_modes():
    outputs = parse_xrandr_query(SAMPLE)

    assert len(outputs) == 1
    assert outputs[0].name == "HDMI-1"
    assert outputs[0].resolutions["1920x1080"] == [60.0, 59.94, 50.0]
    assert outputs[0].resolutions["1280x720"] == [60.0, 59.94]
