import param
import panel as pn
from bokeh.plotting import figure


#todo reformat this to one dict of availble datasets with
# {'half-life':
#      {'color': sadf,
#       'renderer': asdfasdf
#       'export'=True,
#       'description'=}}
# OR make it a param.Parameterized class? This will make autodoc easier
# and we can add methods which will make wildcard names easier


DEFAULT_RENDERERS = {'half-life': 'hex', 'fit1': 'triangle', 'fit2': 'circle', 'TF_rate': 'diamond', 'pfact': 'circle'}
DEFAULT_COLORS = {'half-life': '#f37b21', 'fit1': '#2926e0', 'fit2': '#f20004', 'TF_rate': '#03ab1d', 'pfact': '#16187d',
                  'uptake_corrected': '#000000', 'fr_pfact': '#ba0912'}
DEFAULT_CLASS_COLORS = ['#0e1875', '#fdaf61', '#d73027']  # rigid to flexible
MIN_BORDER_LEFT = 65


class PanelBase(param.Parameterized):
    """base class for mixin panels"""

    position = ''
    panel_name = ''#param.String('', doc="Display name for this panel's tab")''

    @property
    def panel(self):

        return None


class FigurePanel(PanelBase):
    accepted_sources = []
    x_label = ''
    y_label = ''

    def __init__(self, parent, controllers, sources=None, **params):
        super(PanelBase, self).__init__(**params)
        self.parent = parent  # main controller
        self.parent.param.watch(self._parent_sources_updated, ['sources'])
        self.controllers = controllers  # side controllers (update)
        self.figure = self.draw_figure()
        self.bk_pane = pn.pane.Bokeh(self.figure, sizing_mode='stretch_both', name=self.panel_name)

        sources = sources if sources is not None else {}
        self.renderers = {}
        self.add_sources(sources)

    def _parent_sources_updated(self, *events):
        print('updated trigger')
        new_items = {k: v for k, v in self.parent.sources.items() if k in self.accepted_sources and k not in self.renderers}
        self.add_sources(new_items)

    def add_sources(self, src_dict):
        """add a columndatasource object to the figure
        #todo: (if the source is already present it is updated)
        """
        #self.sources.update(src_dict)
        for source in src_dict.values():
            source.on_change('data', self._data_updated_callback)
        self.render_sources(src_dict)

    def remove_sources(self, names):
        """remove source from renderers dict and figure"""
        for name in names:
            renderer = self.renderers[name]
            renderer.data_source.remove_on_change('data', self._data_updated_callback)
            self.figure.renderers.remove(renderer)
            self.renderers.pop(name)

    def render_sources(self, src_dict):
        """override to customize how sources are rendered"""
        for name, source in src_dict.items():
            renderer = self.figure.line('x', 'y', source=source)
            self.renderers[name] = renderer

    def draw_figure(self, **kwargs):
        """Override to create a custom figure with eg to specify axes labels"""

        fig = figure(**kwargs)
        fig.xaxis.axis_label = self.x_label
        fig.yaxis.axis_label = self.y_label

        return fig

    def redraw(self, **kwargs):
        """calls draw_figure to make a new figure and then redraws all renderers"""

        src_dict = self.sources
        self.figure = self.draw_figure(**kwargs)  # todo does the old figure linger on?

        self.renderers = {}
        self.render_sources(src_dict)

        self.bk_pane.object = self.figure

    @property
    def sources(self):
        """returns a dict of the current sources"""
        return {name: renderer.data_source for name, renderer in self.renderers.items()}

    def _data_updated_callback(self, attr, old, new):
        print('data updated callbaçk')
        self.bk_pane.param.trigger('object')

    def update(self):
        self.bk_pane.param.trigger('object')

    @property
    def panel(self):
        return self.bk_pane


class FigurePanelOld(PanelBase):
    """"base class for figures"""

    _controlled_by = []  # list of panel controllers

    def __init__(self, parent, controllers, **params):
        self.parent = parent  #main controller
        self.controllers = controllers  #side controllers
        super(FigurePanelOld, self).__init__(**params)

    def draw_figure(self):
        """Override to create a custom figure with eg to specify axes labels"""
        return figure()

    def _update(self):
        """redraw the graph"""
        self.bk_pane.param.trigger('object')

    @property
    def panel(self):
        return self.bk_pane


class ControlPanel(PanelBase):
    """base class for left control pannels"""

    header = 'Default Header'

    def __init__(self, parent, **params):
        self.parent = parent
        super(ControlPanel, self).__init__(**params)

        self._widget_dict = self.make_dict()
        self._widget_list = self.make_list()  # this list after its made isnt / shouldnt be used?
        self._box = self.make_box()

    def make_box(self):
        #md = pn.pane.Markdown(f'### {self.header}')
        return pn.Card(title = self.header, collapsed=True, *self._widget_list)

    def generate_widgets(self, **kwargs):
        """returns a dict with keys parameter names and values default mapped widgets"""
        return {k: v for k, v in zip(list(self.param)[1:],
                                     pn.Param(self.param, show_name=False, show_labels=True, widgets=kwargs))}

    def make_list(self):
        """override this method to modify mapping of dict to list"""
        return list(self._widget_dict.values())

    def make_dict(self):
        """dict of widgets to be shown
        override this method to get custom mapping

        """
        return self.generate_widgets()

    def box_index(self, p_name_or_widget):
        ""'return the index of the widget in the box with parameter p_name'
        if isinstance(p_name_or_widget, str):
            return list(self._box).index(self._widget_dict[p_name_or_widget])
        else:
            return list(self._box).index(p_name_or_widget)

    def box_pop(self, p_name_or_widget):
        """remove the widget with parameter name name from the box"""
        index = self.box_index(p_name_or_widget)
        self._box.pop(index)

    def box_insert_after(self, name_or_widget_after, name_or_widget_insert):
        """insert widget corresponding to parameter with name after the widget name_after """
        index = self.box_index(name_or_widget_after)
        if isinstance(name_or_widget_insert, str):
            widget = self._widget_dict[name_or_widget_insert]
        else:
            widget = name_or_widget_insert
        self._box.insert(index + 1, widget)

    def get_widget(self, param_name, widget_type, **kwargs):
        """get a single widget with for parameter param_name with type widget_type"""
        return pn.Param.get_widget(getattr(self.param, param_name), widget_type, **kwargs)[0]

    @property
    def panel(self):
        return self._box

#get_widget = pn.Param.get_widget

