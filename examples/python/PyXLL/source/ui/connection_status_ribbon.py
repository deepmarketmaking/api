import logging
# import pyxll
# from pyxll import xl_func

ribbon = None


def Ribbon_Load(ribbon_ui):
    """
    Callback triggered when the ribbon is loaded.
    """
    global ribbon
    ribbon = ribbon_ui
    logging.info("Ribbon loaded and initialized.")
    invalidate_ribbon()


def invalidate_ribbon():
    """
    Forces the ribbon to refresh and call the getLabel and getImage callbacks.
    """
    if ribbon:
        ribbon.InvalidateControl("connectionStatusButton")


# # Register the callbacks with PyXLL
# xl_func(lambda ribbon_ui: Ribbon_Load(ribbon_ui), name="Ribbon_Load")
