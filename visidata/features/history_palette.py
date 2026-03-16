'''History palette: shows previous inputs during search/regex/etc input.'''

from visidata import vd, clipdraw, colors

vd._in_history_palette = False


def _history_palette_hook(vd, prompt, type=None, history=[], updater=lambda v: None, bindings={}, **kwargs):
    '''Input hook: show fuzzy history palette when input has previous history.'''
    _input_rows = kwargs.pop('_input_rows', 0) or 0

    if not type:                        return None
    if not history:                     return None
    if not vd.cursesEnabled:            return None
    if not vd.wantsHelp('cmdpalette'):  return None
    if vd._in_history_palette:          return None

    sheet = vd.activeSheet
    items = list(history)   # 0=oldest .. N-1=newest

    cursor = [-1]       # -1 = free-typing, 0..N-1 = history position
    offset = [0]        # first visible index in navigation mode
    orig = ['']         # saved input before history navigation

    pal_bindings = dict(bindings)

    def _ps():
        return max(1, min(sheet.windowHeight - 3 - _input_rows, vd.options.disp_cmdpal_max))

    def _nav_up(v, i):
        if not items: return v, i
        if cursor[0] == -1:
            orig[0] = v
            cursor[0] = len(items) - 1
            offset[0] = max(0, cursor[0] - _ps() + 1)
        else:
            cursor[0] = max(cursor[0] - 1, 0)
            if cursor[0] < offset[0]:
                offset[0] = cursor[0]
        return items[cursor[0]], len(items[cursor[0]])

    def _nav_down(v, i):
        if not items or cursor[0] == -1: return v, i
        if cursor[0] >= len(items) - 1:
            cursor[0] = -1
        else:
            cursor[0] += 1
            if cursor[0] >= offset[0] + _ps():
                offset[0] = cursor[0] - _ps() + 1
        v = items[cursor[0]] if cursor[0] >= 0 else orig[0]
        return v, len(v)

    def _nav_pgup(v, i):
        if not items: return v, i
        if cursor[0] == -1:
            orig[0] = v
            cursor[0] = len(items) - 1
        cursor[0] = max(cursor[0] - _ps(), 0)
        offset[0] = cursor[0]
        return items[cursor[0]], len(items[cursor[0]])

    def _nav_pgdn(v, i):
        if not items or cursor[0] == -1: return v, i
        cursor[0] = min(cursor[0] + _ps(), len(items) - 1)
        offset[0] = max(cursor[0] - _ps() + 1, 0)
        return items[cursor[0]], len(items[cursor[0]])

    pal_bindings['Up'] = _nav_up
    pal_bindings['Down'] = _nav_down
    pal_bindings['PgUp'] = _nav_pgup
    pal_bindings['PgDn'] = _nav_pgdn

    def _draw_palette(value):
        updater(value)
        scr = sheet._scr
        if not scr: return
        nitems = _ps()
        w = min(100, sheet.windowWidth)

        if cursor[0] >= 0 and value != items[cursor[0]]:
            cursor[0] = -1  # user typed something

        if cursor[0] == -1 and not value:
            return  # no palette when idle

        if cursor[0] >= 0:
            # Navigation mode: show all items, highlight cursor
            ndisplay = min(len(items), nitems)
            vis_start = max(0, min(offset[0], len(items) - ndisplay))
            offset[0] = vis_start
            visible = items[vis_start:vis_start + ndisplay]
            highlight = cursor[0] - vis_start
        else:
            # Fuzzy filter mode
            haystack = [dict(input=item) for item in items]
            matches = vd.fuzzymatch(haystack, value.split())
            if not matches: return
            visible = [m.formatted.get('input', m.match['input']) for m in matches[:nitems]]
            ndisplay = len(visible)
            highlight = -1

        if not visible: return
        box_y = sheet.windowHeight - ndisplay - 2 - _input_rows
        if box_y < 0: return
        pal_cattr = colors.get_color('color_cmdpalette')
        vd.drawBox(scr, 0, box_y, w, ndisplay + 2, pal_cattr, bottom=False)
        for idx, text in enumerate(visible):
            attr = colors.color_menu_spec if idx == highlight else colors.color_cmdpalette
            clipdraw(scr, box_y + 1 + idx, 1, f' {text}', attr, w=w - 2)

    try:
        vd._in_history_palette = True
        return vd.input(prompt, type=type, history=history,
                       updater=_draw_palette, bindings=pal_bindings, **kwargs)
    finally:
        vd._in_history_palette = False


vd._input_hooks.append(_history_palette_hook)
