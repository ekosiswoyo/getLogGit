"""Rounded ttk image elements; native ttk text, focus and keyboard behavior stay intact."""
import math
import tkinter as tk


def rounded_image(master, fill, border, size=28, radius=8):
    image = tk.PhotoImage(master=master, width=size, height=size)
    # Transparent corners let the containing surface show through.
    rows = []
    for y in range(size):
        row = []
        for x in range(size):
            dx = max(radius - x - .5, x + .5 - (size - radius), 0)
            dy = max(radius - y - .5, y + .5 - (size - radius), 0)
            distance = math.hypot(dx, dy)
            row.append(border if distance > radius - 1 or x == 0 or y == 0 or x == size - 1 or y == size - 1 else fill)
        rows.append('{' + ' '.join(row) + '}')
    image.put(' '.join(rows))
    for y in range(size):
        for x in range(size):
            dx = max(radius - x - .5, x + .5 - (size - radius), 0)
            dy = max(radius - y - .5, y + .5 - (size - radius), 0)
            if math.hypot(dx, dy) > radius:
                image.transparency_set(x, y, True)
    return image


def install_rounded_elements(app, palettes):
    style = app.style
    app._rounded_images = []
    for theme, colors in palettes.items():
        for kind in ('primary', 'secondary', 'danger'):
            fill = colors['ACCENT'] if kind == 'primary' else colors['DANGER'] if kind == 'danger' else colors['SECONDARY_BG']
            hover = colors['ACCENT_HOVER'] if kind == 'primary' else colors['DANGER_HOVER'] if kind == 'danger' else colors['SECONDARY_HOVER']
            normal = rounded_image(app, fill, fill)
            active = rounded_image(app, hover, hover)
            disabled = rounded_image(app, colors['DISABLED_BG'], colors['DISABLED_BG'])
            focus = rounded_image(app, fill, colors['ACCENT_HOVER'])
            app._rounded_images.extend((normal, active, disabled, focus))
            element = f'{theme}.{kind}.rounded'
            style.element_create(element, 'image', normal, ('disabled', disabled),
                                 ('pressed', active), ('active', active), ('focus', focus),
                                 border=(9, 4, 9, 4), sticky='nsew')
            name = f'{theme}.{kind.title()}.TButton'
            style.configure(name, background=colors['CARD'])
            style.map(name, background=[(state, colors['CARD']) for state in
                                       ('disabled', 'pressed', 'active', 'focus')])
            style.layout(f'{theme}.{kind.title()}.TButton', [(element, {'sticky': 'nsew', 'children': [
                ('Button.padding', {'sticky': 'nsew', 'children': [('Button.label', {'sticky': 'nsew'})]})]})])
        normal = rounded_image(app, colors['INPUT_BG'], colors['BORDER'])
        focused = rounded_image(app, colors['INPUT_BG'], colors['ACCENT'])
        app._rounded_images.extend((normal, focused))
        element = f'{theme}.rounded.field'
        style.element_create(element, 'image', normal, ('focus', focused), border=(9, 4, 9, 4), sticky='nsew')
        style.layout(f'{theme}.Modern.TEntry', [(element, {'sticky': 'nsew', 'children': [
            ('Entry.padding', {'sticky': 'nsew', 'children': [('Entry.textarea', {'sticky': 'nsew'})]})]})])
        style.layout(f'{theme}.Modern.TCombobox', [(element, {'sticky': 'nsew', 'children': [
            ('Combobox.downarrow', {'side': 'right', 'sticky': 'ns'}),
            ('Combobox.padding', {'sticky': 'nsew', 'children': [('Combobox.textarea', {'sticky': 'nsew'})]})]})])
