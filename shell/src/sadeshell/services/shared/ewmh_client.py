"""Small EWMH fallback for window managers without sadewm's private socket."""
def request(command):
    from Xlib import X, display
    from Xlib.protocol import event
    connection = display.Display()
    try:
        root = connection.screen().root
        def prop(window, name):
            value = window.get_full_property(connection.intern_atom(name), X.AnyPropertyType)
            return value.value if value is not None else []
        current = prop(root, "_NET_CURRENT_DESKTOP")
        desktop = int(current[0]) if len(current) else 0
        if command["cmd"] == "get_state":
            return dict(ok=True, tag_mask=1 << desktop)
        if command["cmd"] == "focus_window":
            window = connection.create_resource_object("window", command["win_id"])
            workspace = prop(window, "_NET_WM_DESKTOP")
            if len(workspace) and int(workspace[0]) != 0xffffffff:
                root.send_event(event.ClientMessage(window=root, client_type=connection.intern_atom("_NET_CURRENT_DESKTOP"),
                                                    data=(32, [int(workspace[0]), X.CurrentTime, 0, 0, 0])),
                                event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
            root.send_event(event.ClientMessage(window=window, client_type=connection.intern_atom("_NET_ACTIVE_WINDOW"),
                                                data=(32, [2, X.CurrentTime, 0, 0, 0])),
                            event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
            connection.flush()
            return dict(ok=True)
        if command["cmd"] != "get_clients":
            return dict(ok=False)
        active = prop(root, "_NET_ACTIVE_WINDOW")
        hidden = connection.intern_atom("_NET_WM_STATE_HIDDEN")
        clients = []
        for ident in prop(root, "_NET_CLIENT_LIST"):
            try:
                window = connection.create_resource_object("window", int(ident))
                geometry = window.get_geometry()
                name = prop(window, "_NET_WM_NAME")
                if isinstance(name, bytes):
                    name = name.decode("utf-8", "replace")
                else:
                    name = window.get_wm_name() or ""
                workspace = prop(window, "_NET_WM_DESKTOP")
                tags = 0xffffffff if len(workspace) and int(workspace[0]) == 0xffffffff else 1 << (int(workspace[0]) if len(workspace) else desktop)
                wm_class = window.get_wm_class() or ("", "")
                clients.append(dict(win_id=int(ident), name=name, **{"class": wm_class[-1]},
                                    tags=tags, focused=bool(len(active) and active[0] == ident),
                                    minimized=hidden in prop(window, "_NET_WM_STATE"),
                                    width=geometry.width, height=geometry.height))
            except Exception:
                continue
        return dict(ok=True, clients=clients)
    finally:
        connection.close()
