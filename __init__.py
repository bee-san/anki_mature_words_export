try:
    from .server import register_server_hooks
    from .ui import register_tools_menu
except ModuleNotFoundError as error:
    if error.name != "aqt":
        raise
else:
    register_tools_menu()
    register_server_hooks()
