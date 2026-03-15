import collections
import math
from functools import partial
from visidata import DrawablePane, BaseSheet, vd, VisiData, CompleteKey, clipdraw, HelpSheet, colors, AcceptInput, AttrDict, drawcache_property, dispwidth, EscapeException


vd.theme_option('color_cmdpalette', 'black on 72', 'base color of command palette')
vd.theme_option('disp_cmdpal_max', 10, 'max number of suggestions for command palette')

vd.help_longname = '''# Choose Command
Start typing a command longname or keyword in its helpstring.

- `Enter` to execute top command.
- `Tab` to highlight top command.

## When Command Highlighted

- `Tab`/`Shift+Tab` to cycle highlighted command.
- `Enter` to execute highlighted command.
- `0-9` to execute numbered command.
'''

def add_to_input(v, i, value=''):
    items = list(v.split())
    if not v or v.endswith(' '):
        items.append(value)
    else:
        items[-1] = value
    v = ' '.join(items) + ' '
    return v, len(v)


def accept_input(v, i, value=None):
    raise AcceptInput(v if value is None else value)

def accept_input_if_subset(v, i, value=''):
    # if no input, accept value under cmd palette cursor
    if not v:
        raise AcceptInput(value)

    # if the last item is a partial match, replace it with the full value
    parts = v.split()
    if value and value.startswith(parts[-1]):
        v = ' '.join(parts[:-1] + [value])

    raise AcceptInput(v)

@VisiData.lazy_property
def usedInputs(vd):
    return collections.defaultdict(int)

@DrawablePane.after
def execCommand2(sheet, cmd, *args, **kwargs):
    vd.usedInputs[cmd.longname] += 1

@BaseSheet.api
def inputPalette(sheet, prompt, items,
                 value_key='key',
                 formatter=lambda m, item, trigger_key: f'{trigger_key} {item}',
                 multiple=False,
                 freeform=False,
                 x=0, y=0, w=0, h=0,
                 **kwargs):
    caller_updater = kwargs.pop('updater', lambda val: None)
    caller_bindings = kwargs.pop('bindings', {})
    caller_completer = kwargs.pop('completer', None)
    input_rows = kwargs.pop('_input_rows', 1)  # number of input field rows to avoid

    if not vd.wantsHelp('cmdpalette'):
        completer = caller_completer or CompleteKey(sorted(item[value_key] for item in items))
        return vd.input(prompt,
                completer=completer,
                updater=caller_updater, bindings=caller_bindings,
                **kwargs)

    bindings = dict(caller_bindings)

    #state variables for navigating display of matches
    prev_value = None
    tabitem = -1
    offset = -1 if freeform else 0
    scroll_locked = False
    def reset_display():
        nonlocal tabitem, offset, scroll_locked
        tabitem = -1
        offset = -1 if freeform else 0  # -1 = anchor at bottom
        scroll_locked = False

    def tab(n, nitems):
        nonlocal tabitem
        if not nitems: return None
        tabitem = (tabitem + n) % nitems

    def _draw_palette(value):
        nonlocal prev_value, h, w, offset, tabitem
        caller_updater(value)
        words = value.split()
        if value != prev_value:
            reset_display()
            prev_value = value

        if multiple and words:
            if value.endswith(' '):
                finished_words = words
                unfinished_words = []
            else:
                finished_words = words[:-1]
                unfinished_words = [words[-1]]
        else:
            finished_words = []
            unfinished_words = words

        unuseditems = [item for item in items if item[value_key] not in finished_words]

        h = h or sheet.windowHeight
        w = w or min(100, sheet.windowWidth)
        nitems = min(h-3, sheet.options.disp_cmdpal_max)
        if nitems <= 0:
            return None

        # in freeform mode, detect history navigation (exact match) vs user typing
        match_idx = -1
        if freeform and value:
            match_idx = next((idx for idx, item in enumerate(unuseditems) if item[value_key] == value), -1)
            if match_idx >= 0:
                unfinished_words = []  # show ordered list, not fuzzy results

        matches = vd.fuzzymatch(unuseditems, unfinished_words)

        if freeform and matches:  # preserve original item order for history
            item_order = {id(item): idx for idx, item in enumerate(items)}
            matches = sorted(matches, key=lambda m: item_order.get(id(m.match), 0))

        useditems = []
        palrows = []
        n_results = 0
        def read_matches(offset):
            nonlocal useditems, palrows, value, n_results

            useditems = []
            palrows = []
            for m in matches[offset:offset+nitems]:
                useditems.append(m.match)
                palrows.append((m, m.match))
            n_results += len(matches)

            #List matches only, usually. But list the available choices when there's no input,
            #or (if multiple is True) they've just pressed space after a word.
            if not unfinished_words:
                favitems = sorted([item for item in unuseditems if item not in useditems],
                                key=lambda item: -vd.usedInputs.get(item[value_key], 0))
                for item in favitems[offset-len(palrows):offset+nitems-len(palrows)]:
                    palrows.append((None, item))
                n_results += len(favitems)

        if match_idx >= 0 and not scroll_locked:  # scroll to and highlight the matched history entry
            total = len(unuseditems)
            if offset < 0:  # initial: anchor at bottom
                offset = max(0, total - nitems)
            if match_idx < offset:  # hit the top edge
                offset = match_idx
            elif match_idx >= offset + nitems:  # hit the bottom edge
                offset = match_idx - nitems + 1
            tabitem = match_idx - offset
        elif offset < 0:  # anchor at bottom (most recent visible)
            total = len(matches) if unfinished_words else len(unuseditems)
            offset = max(0, total - nitems)

        read_matches(offset)

        def change_page(dir=+1):
            nonlocal offset, n_results, nitems
            new_offset = offset + dir*nitems
            # constrain offset to be a multiple of nitems
            new_offset = min(new_offset, ((n_results-1) // nitems)*nitems)
            new_offset = max(new_offset, 0)
            if new_offset == offset: return None
            offset = new_offset

        navailitems = min(len(palrows), nitems)

        if not freeform:
            bindings['Tab'] = lambda *args: tab(1, navailitems) or args
            bindings['Shift+Tab'] = lambda *args: tab(-1, navailitems) or args

        if freeform:
            def _pgup(*args):
                nonlocal scroll_locked
                change_page(-1)
                scroll_locked = True
                return args
            def _pgdn(*args):
                nonlocal scroll_locked
                change_page(+1)
                scroll_locked = True
                return args
            bindings['PgUp'] = _pgup
            bindings['PgDn'] = _pgdn
        else:
            bindings['PgUp'] = lambda *args: (change_page(-1) and read_matches(offset)) or args
            bindings['PgDn'] = lambda *args: (change_page(+1) and read_matches(offset)) or args
        for numkey in '1234567890':
            bindings.pop(numkey, None)

        for i in range(nitems-len(palrows)):
            palrows.append((None, None))

        if not navailitems:
            if freeform:
                bindings.pop('Enter', None)
            else:
                def _enter(v, i):
                    raise EscapeException(f'no choice matching {v}')
                bindings['Enter'] = _enter
            bindings.pop(' ', None)
        pal_cattr = colors.get_color('color_cmdpalette')
        if freeform:
            vd.drawBox(sheet._scr, x, y+h-nitems-input_rows-1, w, nitems+1, pal_cattr, bottom=False)
        else:
            vd.drawBox(sheet._scr, x, y+h-nitems-3, w, nitems+2, pal_cattr, bottom=False)

        used_triggers = set()
        for i, (m, item) in enumerate(palrows):
            trigger_key = ''
            if not freeform and tabitem >= 0 and item:
                tkey = f'{i+1}'[-1]
                if tkey not in used_triggers:
                    trigger_key = tkey
                    bindings[trigger_key] = partial(add_to_input if multiple else accept_input, value=item[value_key])
                    used_triggers.add(trigger_key)

            attr = colors.color_cmdpalette

            if tabitem < 0 and palrows:
                _ , topitem = palrows[0]
                if topitem:
                    if freeform:
                        bindings.pop('Enter', None)
                    elif multiple:
                        bindings['Enter'] = partial(accept_input_if_subset, value=topitem[value_key])
                        bindings['Space'] = partial(add_to_input, value=topitem[value_key])
                    else:
                        bindings['Enter'] = partial(accept_input, value=topitem[value_key])
            elif item and i == tabitem:
                if freeform:
                    bindings.pop('Enter', None)
                elif multiple:
                    bindings['Enter'] = partial(accept_input_if_subset, value=item[value_key])
                    bindings['Space'] = partial(add_to_input, value=item[value_key])
                else:
                    bindings['Enter'] = partial(accept_input, value=item[value_key])
                attr = colors.color_menu_spec

            match_summary = formatter(m, item, trigger_key) if item else ' '

            content_y = y+h-nitems-input_rows+i if freeform else y+h-nitems-2+i
            clipdraw(sheet._scr, content_y, x+1, match_summary, attr, w=w-2)
        if not freeform:
            attr = colors.color_cmdpalette
            instr = 'Press [:keystrokes]PgUp/PgDn[/] to scroll items, [:keystrokes]Tab/Shift+Tab[/] then [:keystrokes]Enter[/] to choose, [:keystrokes]Esc[/] to cancel.'
            if dispwidth(instr) < w-2:
                clipdraw(sheet._scr, h-2, x+1, instr, attr, w=w-2)

        return None

    completer = caller_completer or CompleteKey(sorted(item[value_key] for item in items))
    return vd.input(prompt,
            completer=completer,
            updater=_draw_palette,
            bindings=bindings,
            **kwargs)


def cmdlist(sheet):
    return [
            AttrDict(longname=row.longname,
                     description=sheet.cmddict[(row.sheet, row.longname)].helpstr)
        for row in sheet.rows
    ]
HelpSheet.cmdlist = drawcache_property(cmdlist)


@BaseSheet.api
def inputLongname(sheet):
    prompt = 'command name: '
    # get set of commands possible in the sheet
    this_sheets_help = HelpSheet('', source=sheet)
    vd.sync(this_sheets_help.ensureLoaded())

    def _fmt_cmdpal_summary(match, row, trigger_key):
        keystrokes = this_sheets_help.revbinds.get(row.longname, [None])[0] or ' '
        formatted_longname = match.formatted.get('longname', row.longname) if match else row.longname
        formatted_name = f'[:bold][:onclick {row.longname}]{formatted_longname}[/][/]'
        if vd.options.debug and match:
            keystrokes = f'[{match.score}]'
        r = f' [:keystrokes]{keystrokes.rjust(dispwidth(prompt)-5)}[/]  '
        if trigger_key:
            r += f'[:keystrokes]{trigger_key}[/]'
        else:
            r += ' '

        r += f' {formatted_name}'
        if row.description:
            formatted_desc = match.formatted.get('description', row.description) if match else row.description
            r += f' - {formatted_desc}'
        return r

    return sheet.inputPalette(prompt, this_sheets_help.cmdlist,
                              value_key='longname',
                              formatter=_fmt_cmdpal_summary,
                              help=vd.help_longname,
                              type='longname')

@BaseSheet.api
def inputLongnameSimple(sheet):
    'Input a command longname without using the command palette.'
    longnames = set(k for (k, obj), v in vd.commands.iter(sheet))
    return vd.input("command name: ", completer=CompleteKey(sorted(longnames)), type='longname')


@BaseSheet.api
def exec_longname(sheet, longname):
    if not sheet.getCommand(longname):
        vd.fail(f'no command {longname}')
    sheet.execCommand(longname)


vd.addCommand('Space', 'exec-longname', 'exec_longname(inputLongname())', 'execute command by its longname')
vd.addCommand('zSpace', 'exec-longname-simple', 'exec_longname(inputLongnameSimple())', 'execute command by its longname (without command palette)')


vd.help_input_history = '''# Input History

Type to fuzzy search through previous inputs.
`Up`/`Down` to cycle through history.
`Down` past the newest restores your original text.
`Enter` to accept.
'''


def _history_palette_hook(vd, prompt, type=None, history=[], **kwargs):
    'Show input history in a fuzzy palette when history is available.'
    if getattr(vd, '_in_history_palette', False):
        return None
    if not type or not history or not vd.cursesEnabled:
        return None
    if not vd.wantsHelp('cmdpalette'):
        return None

    sheet = vd.activeSheet

    def _fmt_history(match, item, trigger_key):
        if not item:
            return ' '
        formatted = match.formatted.get('input', item.input) if match else item.input
        r = f'  {trigger_key + " " if trigger_key else "  "}{formatted}'
        return r

    items = [AttrDict(input=h) for h in history]  # oldest first = top, newest = bottom
    kwargs.pop('help', None)

    vd._in_history_palette = True
    try:
        return sheet.inputPalette(prompt, items, value_key='input',
                                  formatter=_fmt_history,
                                  freeform=True,
                                  help=vd.help_input_history,
                                  type=type,
                                  history=history,
                                  **kwargs)
    finally:
        vd._in_history_palette = False


vd._input_hooks.append(_history_palette_hook)
