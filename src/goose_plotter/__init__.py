def main() -> None:
    from goose_plotter.plotter import Plotter

    relaunch = None
    while True:  # a language change closes the window to open it again, in the new one
        window = Plotter(relaunch)
        window.mainloop()
        relaunch = window.relaunch
        if relaunch is None:
            break
