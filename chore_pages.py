"""Reusable Discord page structure, independent of chore rules and storage.

Configure a PageSpec and fill its named slots. The full tree is validated before
it is attached to a live LayoutView; recovery never adds an unbudgeted control.
"""
from dataclasses import dataclass
from enum import Enum
import discord


class PageKind(str, Enum):
    DASHBOARD='dashboard'
    LIST='list'
    DETAIL='detail'
    CALENDAR='calendar'
    FORM='form'
    HELP='help'
    CONFIRM='confirmation'


@dataclass(frozen=True)
class ActionGroup:
    title: str
    labels: tuple[str,...]=()
    prefixes: tuple[str,...]=()
    fallback: bool=False
    menu: bool=False

    def accepts(self,item):
        label=str(getattr(item,'label',''))
        return label in self.labels or bool(self.prefixes and label.startswith(self.prefixes))


CHORE_ACTIONS=(
    ActionGroup('This occurrence',('Claim','Done','Checklist','Skip this occurrence','Undo completion','Stuck / need help','Need help','Choose occurrence','Choose date')),
    ActionGroup('Who does it',('Signup options','Sign-up schedule','Reassign','Drop responsibility','Propose trade','Every week · ongoing'),('Take ','Release ')),
    ActionGroup('Change this chore',('Edit chore','Change schedule','Change regular day','Estimate / checklist','Duplicate chore','Separate AM and PM sign-ups')),
    ActionGroup('More options',fallback=True),
)


@dataclass(frozen=True)
class PageSpec:
    kind: PageKind
    title: str
    help_topic: str='Start here'
    accent: int=0x6B9B77
    action_groups: tuple[ActionGroup,...]=()
    native_choices: bool=False

    def __post_init__(self):
        if not self.title.strip():raise ValueError('Every page needs a title')
        if sum(group.fallback for group in self.action_groups)>1:raise ValueError('Only one fallback action group is allowed')


SCREEN_KINDS={
    'Dashboard':PageKind.DASHBOARD,
    **{name:PageKind.LIST for name in ('Browse','Manage','Attention','Points','ResetHistory','History','Inbox','Trips','Report','NeedsHelp','HelpHistory')},
    **{name:PageKind.DETAIL for name in ('Card','FutureOccurrence','ExceptionCard')},
    'Calendar':PageKind.CALENDAR,'Day':PageKind.CALENDAR,
    'Guide':PageKind.HELP,'PageHelp':PageKind.HELP,
    'Confirm':PageKind.CONFIRM,
}


def page_spec(screen,title,topic='Start here'):
    kind=SCREEN_KINDS.get(screen,PageKind.FORM)
    return PageSpec(kind,title,topic,0x9B59B6 if kind==PageKind.DASHBOARD else 0x6B9B77,
                    CHORE_ACTIONS if screen=='Card' else (),screen in ('PersonalSettings','Filters','RemoveChoreView','EditChoreView','Guide'))


def _count(component):
    return 1+sum(_count(child) for child in component.get('components',[]))+(_count(component['accessory']) if component.get('accessory') else 0)


def component_count(items):
    return sum(_count(item.to_component_dict()) for item in items)


class PageLayoutError(ValueError):
    pass


class PagePlan:
    """Shared shell: title, toolbar, body, page counter, paging, actions, nav, Undo."""
    SLOT_ORDER=('header','toolbar','content','footer','paging','actions','navigation','undo')
    MAX_COMPONENTS=40
    MAX_TEXT=4000

    def __init__(self,spec):
        self.spec=spec
        self.slots={slot:[] for slot in self.SLOT_ORDER}
        self.optional=[]

    @property
    def children(self):
        return [item for slot in self.SLOT_ORDER for item in self.slots[slot]]

    def add_item(self,item,*,slot='actions',optional=False):
        if slot not in self.slots:raise ValueError('Unknown page slot: '+slot)
        if any(item is old for old in self.walk_children()):raise ValueError('A control cannot appear twice on one page')
        if optional and not isinstance(item,discord.ui.Separator):raise ValueError('Only decorative dividers may be optional')
        self.slots[slot].append(item)
        if optional:self.optional.append(item)
        return item

    def remove_item(self,item):
        for items in self.slots.values():
            if item in items:items.remove(item);return

    def walk_children(self):
        for item in self.children:
            yield item
            if hasattr(item,'walk_children'):yield from item.walk_children()

    @property
    def component_count(self):
        return component_count(self.children)

    def rows(self,items,*,slot='actions',width=5):
        items=list(items)
        if not 1<=width<=5:raise ValueError('Discord rows allow one to five buttons')
        for start in range(0,len(items),width):self.add_item(discord.ui.ActionRow(*items[start:start+width]),slot=slot)

    def grouped_actions(self,items,*,guard):
        groups=self.spec.action_groups
        buckets={group.title:[] for group in groups}
        fallback=next((group for group in groups if group.fallback),None)
        for item in items:
            group=next((group for group in groups if group.accepts(item)),fallback)
            if group is None:raise ValueError('Unconfigured action: '+str(getattr(item,'label','')))
            buckets[group.title].append(item)
        for group in groups:
            if not buckets[group.title]:continue
            if not group.menu:
                priority={label:index for index,label in enumerate(group.labels)}
                buckets[group.title].sort(key=lambda item:priority.get(str(getattr(item,'label','')),len(priority)))
                self.add_item(discord.ui.TextDisplay('### '+group.title))
            if group.menu:
                choices=tuple(buckets[group.title])
                if len(choices)>25:raise PageLayoutError('A dropdown supports at most 25 actions')
                picker=discord.ui.Select(placeholder=group.title,options=[discord.SelectOption(label=str(item.label)[:100],value=str(n),description='Unavailable for this occurrence' if item.disabled else None,emoji='🔴' if item.style==discord.ButtonStyle.danger else '🟢' if item.style==discord.ButtonStyle.success else None) for n,item in enumerate(choices)],disabled=all(item.disabled for item in choices))
                picker._sprig_menu_actions=choices
                async def choose(i,picker=picker,choices=choices):
                    if not await guard(i):return
                    try:
                        index=int(picker.values[0])
                        if not 0<=index<len(choices):raise ValueError('Invalid menu option')
                        action=choices[index]
                    except (ValueError,IndexError):return await i.response.send_message('Choose an action from this menu.',ephemeral=True)
                    if action.disabled:return await i.response.send_message('That action is unavailable for this occurrence. Refresh to check the current state.',ephemeral=True)
                    await action.callback(i)
                picker.callback=choose
                self.add_item(discord.ui.ActionRow(picker))
            else:self.rows(buckets[group.title])

    @staticmethod
    def detail_row(content,*,label,callback,navigation=False):
        button=discord.ui.Button(label=label,style=discord.ButtonStyle.secondary)
        button.callback=callback
        button._sprig_navigation=navigation
        return discord.ui.Section(content,accessory=button)

    def paging(self,labels,available):
        by_label={item.label:item for item in available}
        items=[]
        for label in labels:
            item=by_label.get(label)
            if item is None:
                item=discord.ui.Button(label=label,style=discord.ButtonStyle.secondary,disabled=True)
                async def boundary(i):return None
                item.callback=boundary
            items.append(item)
        self.rows(items,slot='paging')

    def heading(self,title,help_button):
        self.add_item(discord.ui.Section(title,accessory=help_button),slot='header')

    def navigation(self,items):
        items=list(items)
        by_label={getattr(item,'label',None):item for item in items}
        # Back and Dashboard never move around when optional controls appear.
        controls=([by_label['Back']] if 'Back' in by_label else [])
        refresh=discord.ui.Button(label='Refresh',style=discord.ButtonStyle.secondary)
        controls.append(refresh)
        if 'Dashboard' in by_label:controls.append(by_label['Dashboard'])
        self.rows(controls,slot='navigation')
        return refresh

    def undo(self,item):
        rows=self.slots['undo']
        if rows and isinstance(rows[-1],discord.ui.ActionRow) and len(rows[-1].children)<5:rows[-1].add_item(item)
        else:self.rows([item],slot='undo')

    def validate(self):
        count=self.component_count
        if count>self.MAX_COMPONENTS:
            raise PageLayoutError(f'{self.spec.title}: planned {count} components; maximum is {self.MAX_COMPONENTS}')
        length=sum(len(item.content) for item in self.walk_children() if isinstance(item,discord.ui.TextDisplay))
        if length>self.MAX_TEXT:raise PageLayoutError(f'{self.spec.title}: planned text exceeds {self.MAX_TEXT} characters')
        buttons=[item for item in self.walk_children() if isinstance(item,(discord.ui.Button,discord.ui.Select,discord.ui.UserSelect))]
        if len({id(item) for item in buttons})!=len(buttons):raise PageLayoutError('A control was configured more than once')
        for item in self.walk_children():
            if isinstance(item,discord.ui.ActionRow) and sum(child.width for child in item.children)>5:
                raise PageLayoutError('A button row exceeds Discord width')
        return count

    def commit(self,panel):
        # Drop decorative dividers only; content, paging, actions, and Undo stay.
        for item in self.optional:
            if self.component_count<=self.MAX_COMPONENTS:break
            self.remove_item(item)
        self.validate()
        for item in self.children:panel.add_item(item)
        return panel


def list_capacity(preferred,*,undo_count=0,grouped=False,tab_count=4):
    """Plan dense list rows against the full header/footer/control footprint.

    Header section=3, frame=1, page counter=1, paging=3, navigation=3.
    Tabs and filters each have their own row; a chore uses one row + 3 buttons.
    Decorative separators do not consume this essential-controls reservation.
    """
    filter_count=4 if grouped else 2
    fixed=14+tab_count+filter_count+(1+undo_count if undo_count else 0)
    return max(1,min(preferred,(PagePlan.MAX_COMPONENTS-fixed)//4))
