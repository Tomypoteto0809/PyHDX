from .log import setup_custom_logger
from .base import ControlPanel
from .fig_panels import CoverageFigure, RateFigure
from pyhdx.pyhdx import PeptideCSVFile, KineticsSeries
from pyhdx.fitting import KineticsFitting
from pyhdx.fileIO import read_dynamx
from pyhdx.support import get_constant_blocks, get_reduced_blocks, fmt_export, np_from_txt, autowrap

logger = setup_custom_logger('root')
logger.debug('main message')


import param
import panel as pn
from jinja2 import Environment, FileSystemLoader
import holoviews as hv  #todo remove dependency
import os
import numpy as np
from skimage.filters import threshold_multiotsu
from numpy.lib.recfunctions import stack_arrays, append_fields

from io import StringIO

import matplotlib
matplotlib.use('agg') # for panel mpl support

from bokeh.util.serialization import make_globally_unique_id




pth = os.path.dirname(__file__)

env = Environment(loader=FileSystemLoader(pth))

empty_results = {
    'fit1': {'rates': {'r_number': [], 'rate': []}},
    'fit2': {'rates': {'r_number': [], 'rate': []}}
}


class Controller(param.Parameterized):
    """
    controller for main panels layout
    and has panels for each tabin the main layout

    """

    data = param.Array()  # might not be needed, in favour of peptides
    #rates = param.Array(doc='Output rates data')
    fit_results = param.Dict(empty_results)
    peptides = param.ClassSelector(PeptideCSVFile)  #class with all peptides to be considered
    series = param.ClassSelector(KineticsSeries)
    fitting = param.ClassSelector(KineticsFitting)

    def __init__(self, template, panels, **params):
        super(Controller, self).__init__(**params)
        template = env.get_template('template.html')

        tmpl = pn.Template(template=template)
     #   tmpl.nb_template.globals['get_id'] = make_globally_unique_id


        # Controllers
        self.fileinput = FileInputControl(self)
        self.coverage = CoverageControl(self)#CoveragePanel(self)
        self.fit_control = FittingControl(self)
        #self.rate_panel = RateConstantPanel(self)
        self.classification_panel = ClassificationControl(self)
        self.file_export = FileExportPanel(self)


        #Figures
        self.coverage_figure = CoverageFigure(self, [self.coverage])  #parent, [controllers]
        self.rate_figure = RateFigure(self, [self.fit_control, self.classification_panel]) # parent, [controllers]  #todo parse as kwargs

        # tmpl = pn.Template(template)
        tmpl.add_panel('input', self.fileinput.panel)
        tmpl.add_panel('coverage', self.coverage.panel)
        tmpl.add_panel('fitting', self.fit_control.panel)
        tmpl.add_panel('classification', self.classification_panel.panel)
        tmpl.add_panel('file_export', self.file_export.panel)
        tmpl.add_panel('coverage_fig', self.coverage_figure.panel)
        tmpl.add_panel('rate_fig', self.rate_figure.panel)
        tmpl.add_panel('slice_k', hv.Curve([1, 2, 3]))


        #tmpl.add_panel('B', hv.Curve([1, 2, 3]))

        self.template = tmpl
      #  self.panels = [panel(self) for panel in panels]

    @param.depends('series', watch=True)
    def _series_changed(self):
        # This is triggered if the fileinput child panel yields a new KineticSeries
        print('series changed')

        self.fitting = KineticsFitting(self.series)
        #todo add errors here
        rate_fields = ['fit1', 'fit1_r1', 'fit1_r2', 'fit2', 'fit2_r1', 'fit2_r2']
        color_fields = ['fit1_color', 'fit2_color']
        dtype = [('r_number', int)] + [(name, float) for name in rate_fields] + [(name, 'U7') for name in color_fields]
        rates = np.zeros(self.series.cov.prot_len, dtype=dtype)
        rates['r_number'] = self.series.cov.r_number
        rates['fit1_color'][:] = 'blue'
        rates['fit2_color'][:] = 'red'

        self.rates = rates  # this assignement triggers downstream watchers? manual trigger?

    @property
    def servable(self):
        return self.template.servable

    def get_rate_file_export(self):
        fmt, header = fmt_export(self.rates)
        s = StringIO()
        np.savetxt(s, fmt=fmt, header=header)

    @param.depends('data')
    def _test(self):
        print("hoi, data changed")


class FileInputControl(ControlPanel):
    add_button = param.Action(lambda self: self._action_add(), doc='Add File', label='Add File')
    clear_button = param.Action(lambda self: self._action_clear(), doc='Clear files', label='Clear Files')
    drop_first = param.Integer(1, bounds=(0, None))
    load_button = param.Action(lambda self: self._action_load(), doc='Load Files', label='Load Files')

    norm_state = param.Selector(doc='State used to normalize uptake', label='Norm State')
    norm_exposure = param.Selector(doc='Exposure used to normalize uptake', label='Norm exposure')

    zero_state = param.Selector(doc='State used to zero uptake', label='Zero state')
    zero_exposure = param.Selector(doc='Exposure used to zero uptake', label='Zero exposure')

    exp_state = param.Selector(doc='State for selected experiment', label='Experiment State')
    exp_exposures = param.ListSelector(default=[], objects=[''], label='Experiment Exposures')

    parse_button = param.Action(lambda self: self._action_parse(), doc='Parse', label='Parse')

    def __init__(self, parent, **params):
        super(FileInputControl, self).__init__(parent, **params)
        self.file_selectors_column = pn.Column(*[pn.widgets.FileInput(accept='.csv')])

    def _action_add(self):
        print('action_add')
        widget = pn.widgets.FileInput(accept='.csv')
        self.file_selectors_column.append(widget)

    def _action_clear(self):
        print('action clear')
        self.file_selectors_column.clear()
        self._action_add()

    def _action_load(self):
        print('action load')
        data_list = []
        for file_selector in self.file_selectors_column:
            if file_selector.value is not None:
                s_io = StringIO(file_selector.value.decode('UTF-8'))
                data = read_dynamx(s_io)
                data_list.append(data)

        combined = stack_arrays(data_list, asrecarray=True, usemask=False, autoconvert=True)

        self.parent.data = combined
        self.parent.peptides = PeptideCSVFile(self.parent.data, drop_first=self.drop_first)

        states = list(np.unique(self.parent.peptides.data['state']))
        self.param['norm_state'].objects = states
        self.norm_state = states[0]
        self.param['zero_state'].objects = ['None'] + states
        self.zero_state = 'None'

    def _action_parse(self):
        print('parse action')
        control_0 = (self.zero_state, self.zero_exposure) if self.zero_state != 'None' else None
        self.parent.peptides.set_control((self.norm_state, self.norm_exposure), control_0=control_0, remove_nan=True)
        data_states = self.parent.peptides.data[self.parent.peptides.data['state'] == self.exp_state]
        data = data_states[np.isin(data_states['exposure'], self.exp_exposures)]
        series = KineticsSeries(data)
        series.make_uniform()  #TODO add gui control for this

        self.parent.series = series

    @param.depends('norm_state', watch=True)
    def _update_norm_exposure(self):
        b = self.parent.peptides.data['state'] == self.norm_state
        data = self.parent.peptides.data[b]
        exposures = list(np.unique(data['exposure']))
        self.param['norm_exposure'].objects = exposures
        if exposures:
            self.norm_exposure = exposures[0]

    @param.depends('zero_state', watch=True)
    def _update_zero_exposure(self):
        b = self.parent.peptides.data['state'] == self.zero_state
        data = self.parent.peptides.data[b]
        exposures = list(np.unique(data['exposure']))
        self.param['zero_exposure'].objects = exposures
        if exposures:
            self.control_exposure = exposures[0]

    @param.depends('norm_state', 'norm_exposure', watch=True)
    def _update_experiment(self):
        # r = str(np.random.rand())
        # self.param['exp_state'].objects = [r]
        # self.exp_state = r
        #TODO THIS needs to be updated to also incorporate the zero
        print(self.norm_state, self.norm_exposure)
        pm_dict = self.parent.peptides.return_by_name(self.norm_state, self.norm_exposure)
        states = list(np.unique([v.state for v in pm_dict.values()]))
        self.param['exp_state'].objects = states
        self.exp_state = states[0]

    @param.depends('exp_state', watch=True)
    def _update_experiment_exposure(self):
        b = self.parent.data['state'] == self.exp_state
        exposures = list(np.unique(self.parent.data['exposure'][b]))
        exposures.sort()
        self.param['exp_exposures'].objects = exposures  #todo refactor exposures
        self.exp_exposures = exposures

    @property
    def panel(self):
        params = pn.panel(self.param)
        col = pn.Column(*[self.file_selectors_column, *params[1:]])

        return pn.WidgetBox(col,  pn.layout.VSpacer(), css_classes=['widget-box', 'custom-wbox'], sizing_mode='stretch_height')


class CoverageControl(ControlPanel):
    wrap = param.Integer(25, bounds=(0, None), doc='Number of peptides vertically before moving to the next row') # todo auto?
    aa_per_subplot = param.Integer(100, label='Amino acids per subplot')
    labels = param.Boolean(False, label='Labels')
    index = param.Integer(0, bounds=(0, None), doc='Current index of coverage plot in time')

    def __init__(self, parent, **params):
        super(CoverageControl, self).__init__(parent, **params)
        self.exposure_str = pn.widgets.StaticText(name='Exposure', value='0') # todo update to some param?
        self.parent.param.watch(self._update_series, ['series'])

    @property
    def peptide_measurement(self):
        return self.parent.series[self.index]

    def _update_series(self, event):
        print('coverage new series update index bounds')
        #also update aa per subplot

        self.param['index'].bounds = (0, len(event.new) - 1)
        self.exposure_str.value = str(self.peptide_measurement.exposure)

        step = 25
        value = int(step*(self.parent.series.cov.end // step + 1))
        self.aa_per_subplot = value# triggers redraw

        #must be uniform
        self.wrap = autowrap(self.parent.series.cov)

    @param.depends('index', watch=True)
    def _update_index(self):
        self.exposure_str.value = str(self.peptide_measurement.exposure)

    @property
    def panel(self):
        col = pn.Column(self.param, self.exposure_str)
        #p = pn.Param(self.param, widgets={'file': pn.widgets.FileInput}) for exposure
        return pn.WidgetBox(col, pn.layout.VSpacer(), css_classes=['widget-box', 'custom-wbox'],
                            sizing_mode='stretch_height')


class FittingControl(ControlPanel):
    chisq_thd = param.Number(20, doc='Threshold for chi2 to switch to Differential evolution')
    r_max = param.Number(27, doc='Ceil value for rates')  # Update this value

    do_fit1 = param.Action(lambda self: self._action_fit1())
    block_mode = param.ObjectSelector(default='reduced', objects=['reduced', 'original', 'constant'])

    #todo generate from func signature?
    #block mode reduced params
    max_combine = param.Integer(2, doc='Neighbouring blocks up to and including this size are merged together')
    max_join = param.Integer(5, doc='Blocks up to and including this size are joined with their smallest neighbour')

    #constant block params
    block_size = param.Integer(10, doc='Size of the blocks in constant blocks mode')
    initial_block = param.Integer(5, doc='Size of the initial block in constant block mode')
    show_blocks = param.Boolean(False, doc='Show bounds of blocks in graph')

    do_fit2 = param.Action(lambda self: self._action_fit2(), constant=True)

    def __init__(self, parent, **params):
        super(FittingControl, self).__init__(parent, **params)

        self.block_column = pn.Column(*[self.param[key] for key in ['max_combine', 'max_join']])
        self.parent.param.watch(self._update_series, ['series'])

    def _update_series(self, *events):
        self.r_max = np.log(1 - 0.98) / -self.parent.series.times[1]  # todo user input 0.98

    def _action_fit1(self):
        print('fitting 1')
        #todo context manager?
        self.param['do_fit1'].constant = True
        self.param['do_fit2'].constant = True

        fit_result = self.parent.fitting.weighted_avg_fit(chisq_thd=self.chisq_thd)
        rates_array = fit_result.get_output(['rate', 'tau', 'tau1', 'tau2', 'r'])

        self.parent.fit_results['fit1'] = {'rates': rates_array, 'fitresult': fit_result}
        self.parent.param.trigger('fit_results')  # Trigger plot update


        #self.parent.param.trigger('rates')
        #self._renew(None)  #manual trigger

        self.param['do_fit1'].constant = False
        self.param['do_fit2'].constant = False

    def _action_fit2(self):
        print('fitting 2')
        #todo context manager
        self.param['do_fit1'].constant = True
        self.param['do_fit2'].constant = True

        fit_result = self.parent.fitting.lsq_fit_blocks(self.parent.fit_results['fit1']['rates'], **self.fit_kwargs)
        rates_array = fit_result.get_output(['rate', 'tau', 'tau1', 'tau2', 'r'])
        self.parent.fit_results['fit2'] = {'rates': rates_array, 'fitresult': fit_result}

#        self.parent.param.trigger('rates')

  #      self._renew(None)  # manual trigger
        self.parent.param.trigger('fit_results')  # Trigger plot update

        self.param['do_fit1'].constant = False
        self.param['do_fit2'].constant = False

    @property
    def fit_kwargs(self):
        if self.block_mode == 'reduced':
            fit_kwargs = {'block_func': get_reduced_blocks, 'max_combine': self.max_combine, 'max_join': self.max_join}
        elif self.block_mode == 'original':
            fit_kwargs = {'block_func': lambda series, **kwargs: series.cov.block_length}
        elif self.block_mode == 'constant':
            fit_kwargs = {'block_func': get_constant_blocks, 'block_size': self.block_size, 'initial_block': self.initial_block}
        return fit_kwargs

    @param.depends('block_mode', watch=True)
    def _update_block_mode(self):
        print('block mode updated')
        if self.block_mode == 'reduced':
            self.block_column.clear()
            [self.block_column.append(self.param[key]) for key in ['max_combine', 'max_join']]
        elif self.block_mode == 'original':
            self.block_column.clear()
        elif self.block_mode == 'constant':
            self.block_column.clear()
            [self.block_column.append(self.param[key]) for key in ['block_size', 'initial_block']]

    @property
    def panel(self):
        par1 = ['chisq_thd', 'r_max', 'do_fit1', 'block_mode']
        par2 = ['do_fit2']
        pars = [self.param[key] for key in par1] + [self.block_column] + [self.param[key] for key in par2]
        return pn.WidgetBox(*pars)


class ClassificationControl(ControlPanel):
    num_classes = param.Number(3, bounds=(1, None), doc='Number of classification classes')
    target = param.Selector(label='Target')
    otsu_thd = param.Action(lambda self: self._action_threshold(), label='Otsu')
    values = param.List(precedence=-1)
    colors = param.List(precedence=-1)

    color_defaults = ['#1930e0', '#eded0e', '#cc0c49']

    def __init__(self, parent, **param):
        super(ClassificationControl, self).__init__(parent, **param)

        self.values_col = pn.Column()
        for _ in range(self.num_classes - 1):
            self._add_value()

        self.colors_col = pn.Column()
        for _ in range(self.num_classes):
            self._add_color()

        self.param.trigger('values')
        self.param.trigger('colors')
        self.parent.param.watch(self._rates_updated, ['fit_results'])

    def _rates_updated(self, *events):
        print('rates')
        objects = [elem for elem in ['fit1', 'fit2'] if not np.all(self.parent.rates[elem] == 0)]
        print(objects)
        self.param['target'].objects = objects
        if not self.target and objects:
            self.target = objects[-1]

    def _action_threshold(self):
        if self.num_classes > 1:
            rates = self.parent.fit_results[self.target]['rates']['rate']
            thd_rates = rates[~np.isnan(rates)]
            thds = threshold_multiotsu(np.log(thd_rates), classes=self.num_classes)
            for thd, widget in zip(thds, self.values_col):
                widget.value = np.exp(thd)
        self._do_thresholding()

    def _do_thresholding(self):
        # perhaps we need a class to handle fitting output which has this method
        # yes we do. for all fitting not just fit1
        # alright great. now stop talking to yourself and get back to worK!
        # #quarantine

        # dont do thresholding if the following criteria are met
        if 0 in self.values:
            return
        elif np.any(np.diff(self.values)) < 0:
            return

        rates = self.parent.rates[self.target]
        colors = np.empty(len(self.parent.rates), dtype='U7')

        if self.num_classes == 1:
            colors[:] = self.colors[0]
        else:
            full_thds = [-np.inf] + self.values + [np.inf]
            for lower, upper, color in zip(full_thds[:-1], full_thds[1:], self.colors):
                b = (rates > lower) & (rates <= upper)
                colors[b] = color

        name = self.target + '_color'
       # if 'color' in self.parent.rates.dtype.names:
        self.parent.rates[name] = colors
        self.parent.param.trigger('rates')
        # else:
        #     #perhaps the rates should be a pandas dataframe
        #     rates = append_fields(self.parent.rates, 'color', data=colors, usemask=False)
        #     self.parent.rates = rates  #triggers


    @param.depends('num_classes', watch=True)
    def _update_num_colors(self):
        while len(self.colors_col) != self.num_classes:
            if len(self.colors_col) > self.num_classes:
                self._remove_color()
            elif len(self.colors_col) < self.num_classes:
                self._add_color()
        self.param.trigger('colors')

    @param.depends('num_classes', watch=True)
    def _update_num_values(self):
        while len(self.values_col) != self.num_classes - 1:
            if len(self.values_col) > self.num_classes - 1:
                self._remove_value()
            elif len(self.values_col) < self.num_classes - 1:
                self._add_value()
        self.param.trigger('values')

    def _add_value(self):
        default = 0.0
        self.values.append(default)

        name = 'Threshold {}'.format(len(self.values_col) + 1)
        widget = pn.widgets.LiteralInput(name=name, value=default)
       # widget.param['value'].bounds = (0, None)
        self.values_col.append(widget)
        widget.param.watch(self._value_event, ['value'])

    def _remove_value(self):
        widget = self.values_col.pop(-1)
        self.values.pop(-1)
        [widget.param.unwatch(watcher) for watcher in widget.param._watchers]
        del widget

    def _add_color(self):
        try:
            default = self.color_defaults[len(self.colors_col)]
        except IndexError:
            default = '#FFFFFF'

        self.colors.append(default)
        widget = pn.widgets.ColorPicker(value=default)
        self.colors_col.append(widget)
        widget.param.watch(self._color_event, ['value'])

    def _remove_color(self):
        widget = self.colors_col.pop(-1)
        self.colors.pop(-1)
        [widget.param.unwatch(watcher) for watcher in widget.param._watchers]
        del widget

    #todo jslink?
    def _color_event(self, *events):
        print('color event')
        for event in events:
            idx = list(self.colors_col).index(event.obj)
            self.colors[idx] = event.new
        self.param.trigger('colors')

    def _value_event(self, *events):
        print('value event')
        for event in events:
            idx = list(self.values_col).index(event.obj)
            self.values[idx] = event.new
        self.param.trigger('values')



    @property
    def panel(self):
        return pn.WidgetBox(pn.Param(self.param), self.values_col, self.colors_col)


class FileExportPanel(ControlPanel):


    @property
    def panel(self):
        return pn.WidgetBox(pn.widgets.FileDownload(file='test.html', auto=False))
