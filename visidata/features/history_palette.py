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

    # display: list of (formatted_text, raw_value); shared between draw and nav
    display = [[(item, item) for item in items]]
    cursor = [-1]       # -1 = free-typing, 0..N-1 = index into display
    top = [0]           # first visible index
    orig = ['']         # saved input before history navigation

    pal_bindings = dict(bindings)
    input_height = max(_input_rows, 1)  # at least 1 row for the prompt

    def _nvis():
        return max(1, min(sheet.windowHeight - 2 - input_height, vd.options.disp_cmdpal_max))

    def _bounds():
        'Clamp cursor and top, then enforce cursor visibility (spec rules).'
        n = len(display[0])
        if n == 0: return
        nv = _nvis()
        cursor[0] = max(0, min(cursor[0], n - 1))
        top[0] = max(0, min(top[0], n - 1))
        if top[0] > cursor[0]:              top[0] = cursor[0]
        if top[0] + nv - 1 < cursor[0]:     top[0] = cursor[0] - nv + 1

    def _enter_nav(v):
        'Save orig and place cursor at end of display list.'
        orig[0] = v
        cursor[0] = len(display[0]) - 1
        top[0] = max(0, cursor[0] - _nvis() + 1)

    def _sel():
        'Return (value, cursor_pos) for current cursor selection.'
        v = display[0][cursor[0]][1]
        return v, len(v)

    def _nav_up(v, i):
        if not display[0]: return v, i
        if cursor[0] == -1:
            _enter_nav(v)
        else:
            cursor[0] -= 1
            _bounds()
        return _sel()

    def _nav_down(v, i):
        if not display[0] or cursor[0] == -1: return v, i
        if cursor[0] >= len(display[0]) - 1:
            cursor[0] = -1
            return orig[0], len(orig[0])
        cursor[0] += 1
        _bounds()
        return _sel()

    def _nav_pgup(v, i):
        if not display[0]: return v, i
        if cursor[0] == -1: _enter_nav(v)
        nv = _nvis()
        old_top = top[0]
        cursor[0] -= nv - 1
        top[0] = old_top - nv + 1      # bottom = old top
        _bounds()
        return _sel()

    def _nav_pgdn(v, i):
        if not display[0] or cursor[0] == -1: return v, i
        nv = _nvis()
        old_bottom = top[0] + nv - 1
        cursor[0] += nv - 1
        top[0] = old_bottom             # top = old bottom
        _bounds()
        return _sel()

    def _nav_home(v, i):
        if cursor[0] == -1: return v, 0  # text cursor to start of line
        cursor[0] = 0
        top[0] = 0
        return _sel()

    def _nav_end(v, i):
        if cursor[0] == -1: return v, len(v)  # text cursor to end of line
        cursor[0] = len(display[0]) - 1
        _bounds()
        return _sel()

    pal_bindings['Up'] = _nav_up
    pal_bindings['Down'] = _nav_down
    pal_bindings['PgUp'] = _nav_pgup
    pal_bindings['PgDn'] = _nav_pgdn
    pal_bindings['Home'] = _nav_home
    pal_bindings['End'] = _nav_end

    def _draw_palette(value):
        updater(value)
        scr = sheet._scr
        if not scr: return
        nv = _nvis()
        w = min(100, sheet.windowWidth)

        if cursor[0] >= 0 and value != display[0][cursor[0]][1]:
            cursor[0] = -1  # user typed something

        if cursor[0] == -1:
            # Recompute display list (nav bindings read this on next keypress)
            if value:
                haystack = [dict(input=item) for item in items]
                matches = vd.fuzzymatch(haystack, value.split())
                display[0] = [(m.formatted.get('input', m.match['input']), m.match['input']) for m in matches]
            else:
                display[0] = [(item, item) for item in items]
                return  # no draw when idle

        if not display[0]: return
        ndisplay = min(len(display[0]), nv)

        if cursor[0] >= 0:
            vis_start = max(0, min(top[0], len(display[0]) - ndisplay))
            top[0] = vis_start
            highlight = cursor[0] - vis_start
        else:
            vis_start = 0  # best matches at top
            highlight = -1

        visible = display[0][vis_start:vis_start + ndisplay]
        if not visible: return
        box_y = sheet.windowHeight - ndisplay - input_height - 1
        if box_y < 0: return
        pal_cattr = colors.get_color('color_cmdpalette')
        vd.drawBox(scr, 0, box_y, w, ndisplay + 1, pal_cattr, bottom=False)
        for idx, (text, raw) in enumerate(visible):
            if idx == highlight:
                clipdraw(scr, box_y + 1 + idx, 1, f'> {text}', colors.color_menu_spec, w=w - 2)
            else:
                clipdraw(scr, box_y + 1 + idx, 1, f'  {text}', colors.color_cmdpalette, w=w - 2)

    try:
        vd._in_history_palette = True
        return vd.input(prompt, type=type, history=history,
                       updater=_draw_palette, bindings=pal_bindings, **kwargs)
    finally:
        vd._in_history_palette = False


vd._input_hooks.append(_history_palette_hook)
