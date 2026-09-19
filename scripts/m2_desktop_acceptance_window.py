"""User-launched harmless target for the pending M2 desktop acceptance check.

No file, account, network or desktop automation operations. Closing the window
discards all text. Run explicitly; this is never launched by ordinary tests.
"""
import tkinter as tk


def main():
    window = tk.Tk()
    window.title('OLIVE M2 local acceptance target')
    window.geometry('540x220')
    tk.Label(window, text='Local acceptance target — no data is saved').pack(pady=16)
    value = tk.StringVar()
    tk.Entry(window, textvariable=value, width=48).pack(pady=8)
    status = tk.StringVar(value='No check performed')
    tk.Button(window, text='Check text', command=lambda: status.set(
        'Verified: OLIVE local acceptance' if value.get() == 'OLIVE local acceptance'
        else 'Text does not match the acceptance phrase')).pack(pady=8)
    tk.Label(window, textvariable=status).pack()
    window.mainloop()


if __name__ == '__main__':
    main()
