from .log import setup_custom_logger
from .base import ControlPanel, DEFAULT_COLORS, DEFAULT_CLASS_COLORS
from .fig_panels import CoverageFigure, RateFigure, ProteinFigure, FitResultFigure
from pyhdx.pyhdx import PeptideCSVFile, KineticsSeries
from pyhdx.fitting import KineticsFitting
from pyhdx.fileIO import read_dynamx
from pyhdx.support import get_constant_blocks, get_reduced_blocks, fmt_export, np_from_txt, autowrap

logger = setup_custom_logger('root')
logger.debug('main message')


import param
import panel as pn
from jinja2 import Environment, FileSystemLoader
#import holoviews as hv  #todo remove dependency
import os
import numpy as np
from skimage.filters import threshold_multiotsu
from numpy.lib.recfunctions import stack_arrays, append_fields
from .base import get_widget
from io import StringIO, BytesIO

import matplotlib
matplotlib.use('agg') # for panel mpl support




#dev only
import pickle


from bokeh.util.serialization import make_globally_unique_id
pth = os.path.dirname(__file__)

env = Environment(loader=FileSystemLoader(pth))

# todo dict comprehension

dic = {'rates': np.zeros(0, dtype=[('r_number', int), ('rate', float)]),
       'fitresult': None}

empty_results = {
    'fit1': dic.copy(),
    'fit2': dic.copy()
}


class Controller(param.Parameterized):
    """
    controller for main panels layout
    and has panels for each tabin the main layout

    """

    data = param.Array()  # might not be needed, in favour of peptides
    #rates = param.Array(doc='Output rates data')
    fit_results = param.Dict(empty_results)
    rate_colors = param.Dict({})
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
        self.fit_quality = FittingQuality(self)
        #self.rate_panel = RateConstantPanel(self)
        self.classification_panel = ClassificationControl(self)
        self.file_export = FileExportPanel(self)
        self.options = OptionsPanel(self)
        self.dev = DeveloperPanel(self)

        #Figures
        self.coverage_figure = CoverageFigure(self, [self.coverage])  #parent, [controllers]
        self.rate_figure = RateFigure(self, [self.fit_control, self.classification_panel]) # parent, [controllers]  #todo parse as kwargs
        self.fit_result_figure = FitResultFigure(self, [self.fit_quality])
        self.protein_figure = ProteinFigure(self, [])


        #setup options  #todo automate figure out cross dependencies
        self.options.cov_fig_panel = self.coverage_figure
        self.options.rate_fig_panel = self.rate_figure
        self.options.coverage_ctrl = self.coverage

        # tmpl = pn.Template(template)
        tmpl.add_panel('input', self.fileinput.panel)
        tmpl.add_panel('coverage', self.coverage.panel)
        tmpl.add_panel('fitting', self.fit_control.panel)
        tmpl.add_panel('fit_quality', self.fit_quality.panel)
        tmpl.add_panel('classification', self.classification_panel.panel)
        tmpl.add_panel('file_export', self.file_export.panel)
        tmpl.add_panel('options', self.options.panel)
        tmpl.add_panel('dev', self.dev.panel)

        tmpl.add_panel('coverage_fig', self.coverage_figure.panel)
        tmpl.add_panel('rate_fig', self.rate_figure.panel)
        tmpl.add_panel('fitres_fig', self.fit_result_figure.panel)
        tmpl.add_panel('slice_k', self.protein_figure.panel)
        #tmpl.add_panel('B', hv.Curve([1, 2, 3]))

        self.template = tmpl
      #  self.panels = [panel(self) for panel in panels]

    @param.depends('series', watch=True)
    def _series_changed(self):
        # This is triggered if the fileinput child panel yields a new KineticSeries
        print('series changed')

        self.fitting = KineticsFitting(self.series)
        for key in ['fit1', 'fit2']:    # todo this list of names somewhere?
            self.rate_colors[key] = [DEFAULT_COLORS[key]]*len(self.series.cov.r_number)
        self.param.trigger('rate_colors')

        # #todo add errors here
        # rate_fields = ['fit1', 'fit1_r1', 'fit1_r2', 'fit2', 'fit2_r1', 'fit2_r2']
        # color_fields = ['fit1_color', 'fit2_color']
        # dtype = [('r_number', int)] + [(name, float) for name in rate_fields] + [(name, 'U7') for name in color_fields]
        # rates = np.zeros(self.series.cov.prot_len, dtype=dtype)
        # rates['r_number'] = self.series.cov.r_number
        # rates['fit1_color'][:] = 'blue'
        # rates['fit2_color'][:] = 'red'
        #
        # self.rates = rates  # this assignement triggers downstream watchers? manual trigger?

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
    header = 'Input'

    add_button = param.Action(lambda self: self._action_add(), doc='Add File', label='Add File')
    clear_button = param.Action(lambda self: self._action_clear(), doc='Clear files', label='Clear Files')
    drop_first = param.Integer(1, bounds=(0, None))
    ignore_prolines = param.Boolean(True, doc='Set to True to ignore prolines in the sequence')
    load_button = param.Action(lambda self: self._action_load(), doc='Load Files', label='Load Files')

    norm_mode = param.Selector(doc='Select method of normalization', label='Norm mode', objects=['Exp', 'Theory'])

    norm_state = param.Selector(doc='State used to normalize uptake', label='Norm State')
    norm_exposure = param.Selector(doc='Exposure used to normalize uptake', label='Norm exposure')
    be_percent = param.Number(28., bounds=(0, 100), doc='Percentage of exchangeable deuteriums which backexchange',
                              label='Back exchange percentage')

    zero_state = param.Selector(doc='State used to zero uptake', label='Zero state')
    zero_exposure = param.Selector(doc='Exposure used to zero uptake', label='Zero exposure')

    exp_state = param.Selector(doc='State for selected experiment', label='Experiment State')
    exp_exposures = param.ListSelector(default=[], objects=[''], label='Experiment Exposures')

    parse_button = param.Action(lambda self: self._action_parse(), doc='Parse', label='Parse')

    def __init__(self, parent, **params):
        self.file_selectors = [pn.widgets.FileInput(accept='.csv')]
        super(FileInputControl, self).__init__(parent, **params)

    def make_dict(self):
        return self.generate_widgets(norm_mode=pn.widgets.RadioButtonGroup, be_percent=pn.widgets.LiteralInput)

    def make_list(self):
        parameters = ['add_button', 'clear_button', 'drop_first', 'ignore_prolines', 'load_button',
                      'norm_mode', 'norm_state', 'norm_exposure', 'exp_state', 'exp_exposures', 'parse_button']
        first_widgets = list([self._widget_dict[par] for par in parameters])
        return self.file_selectors + first_widgets

    def _action_add(self):
        print('action_add')
        widget = pn.widgets.FileInput(accept='.csv')
        i = len(self.file_selectors) + 1 # position to insert the new file selector into the widget box
        self.file_selectors.append(widget)
        self._box.insert(i, widget)

    def _action_clear(self):
        print('action clear')

        while self.file_selectors:
            fs = self.file_selectors.pop()
            #todo allow popping/locking with both widgets and parameter names?
            idx = list(self._box).index(fs)
            self._box.pop(idx)
        self._action_add()

    def _action_load(self):
        print('action load')
        data_list = []
        for file_selector in self.file_selectors:
            if file_selector.value is not None:
                s_io = StringIO(file_selector.value.decode('UTF-8'))
                data = read_dynamx(s_io)
                data_list.append(data)

        combined = stack_arrays(data_list, asrecarray=True, usemask=False, autoconvert=True)

        self.parent.data = combined
        self.parent.peptides = PeptideCSVFile(self.parent.data,
                                              drop_first=self.drop_first, ignore_prolines=self.ignore_prolines)

        states = list(np.unique(self.parent.peptides.data['state']))
        self.param['norm_state'].objects = states
        self.norm_state = states[0]
        self.param['zero_state'].objects = ['None'] + states
        self.zero_state = 'None'

    def _action_parse(self):
        print('parse action')
        if self.norm_mode == 'Exp':
            control_0 = (self.zero_state, self.zero_exposure) if self.zero_state != 'None' else None
            self.parent.peptides.set_control((self.norm_state, self.norm_exposure), control_0=control_0, remove_nan=True)
        elif self.norm_mode == 'Theory':
            self.parent.peptides.set_backexchange(self.be_percent)

        data_states = self.parent.peptides.data[self.parent.peptides.data['state'] == self.exp_state]
        data = data_states[np.isin(data_states['exposure'], self.exp_exposures)]

        # states = self.parent.peptides.groupby_state()
        # series = states[self.exp_state]
        # series.make_uniform()

        # b = np.isin(series.full_data['exposure'], self.exp_exposures)
        # data = series.full_data[b].copy()


        #series = KineticsSeries(data)
        #series.make_uniform()  #TODO add gui control for this

        series = KineticsSeries(data, drop_first=self.drop_first, ignore_prolines=self.ignore_prolines)
        series.make_uniform()
        self.parent.series = series

    @param.depends('norm_mode', watch=True)
    def _update_norm_mode(self):

        if self.norm_mode == 'Exp':
            self.box_pop('be_percent')
            self.box_insert_after('norm_mode', 'norm_state')
            self.box_insert_after('norm_state', 'norm_exposure')
            #self._update_experiment()  dont think this is needed
        elif self.norm_mode == 'Theory':
            self.box_pop('norm_state')
            self.box_pop('norm_exposure')
            self.box_insert_after('norm_mode', 'be_percent')

            states = np.unique(self.parent.data['state'])
            self.param['exp_state'].objects = states
            self.exp_state = states[0] if not self.exp_state else self.exp_state

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
        self.exp_state = states[0] if not self.exp_state else self.exp_state

    @param.depends('exp_state', watch=True)
    def _update_experiment_exposure(self):
        b = self.parent.data['state'] == self.exp_state
        exposures = list(np.unique(self.parent.data['exposure'][b]))
        exposures.sort()
        self.param['exp_exposures'].objects = exposures  #todo refactor exposures
        self.exp_exposures = exposures


class CoverageControl(ControlPanel):
    header = 'Coverage'

    wrap = param.Integer(25, bounds=(0, None), doc='Number of peptides vertically before moving to the next row') # todo auto?
    aa_per_subplot = param.Integer(100, label='Amino acids per subplot')
    labels = param.Boolean(False, label='Labels')
    index = param.Integer(0, bounds=(0, 10), doc='Current index of coverage plot in time')

    def __init__(self, parent, **params):
        self.exposure_str = pn.widgets.StaticText(name='Exposure', value='0') # todo update to some param?
        super(CoverageControl, self).__init__(parent, **params)
        self.parent.param.watch(self._update_series, ['series'])

    def make_list(self):
        lst = super(CoverageControl, self).make_list()
        return lst + [self.exposure_str]

    def make_dict(self):
        return self.generate_widgets(index=pn.widgets.IntSlider)

    @property
    def peptide_measurement(self):
        if self.parent.series is not None:
            return self.parent.series[self.index]
        else:
            return None

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

        #set index to zero
        self.index = 0

    @param.depends('index', watch=True)
    def _update_index(self):
        self.exposure_str.value = str(self.peptide_measurement.exposure)

    # @property
    # def panel(self):
    #     col = pn.Column(self.param, self.exposure_str)
    #     #p = pn.Param(self.param, widgets={'file': pn.widgets.FileInput}) for exposure
    #     return pn.WidgetBox(col, pn.layout.VSpacer(), css_classes=['widget-box', 'custom-wbox'],
    #                         sizing_mode='stretch_height')


class FittingControl(ControlPanel):
    header = 'Rate Fitting'

    r_max = param.Number(27, doc='Ceil value for rates')  # Update this value
    chisq_thd = param.Number(20, doc='Threshold for chi2 to switch to Differential evolution')

    do_fit1 = param.Action(lambda self: self._action_fit1())
    block_mode = param.ObjectSelector(default='reduced', objects=['reduced', 'original', 'constant'])

    #todo generate from func signature?
    #block mode reduced params
    max_combine = param.Integer(2, doc='Neighbouring blocks up to and including this size are merged together')
    max_join = param.Integer(5, doc='Blocks up to and including this size are joined with their smallest neighbour')

    #constant block params
    block_size = param.Integer(10, doc='Size of the blocks in constant blocks mode')
    initial_block = param.Integer(5, doc='Size of the initial block in constant block mode')

    do_fit2 = param.Action(lambda self: self._action_fit2(), constant=True)

    def __init__(self, parent, **params):
        super(FittingControl, self).__init__(parent, **params)

        self.block_column = pn.Column(*[self.param[key] for key in ['max_combine', 'max_join']])
        self.parent.param.watch(self._update_series, ['series'])

    def make_list(self):
        text_f1 = pn.widgets.StaticText(name='Weighted averaging fit (Fit 1)')
        text_f2 = pn.widgets.StaticText(name='Global fit (Fit 2)')

        self._widget_dict.update(text_f1=text_f1, text_f2=text_f2)
        parameters = ['r_max', 'text_f1', 'chisq_thd', 'do_fit1', 'text_f2', 'block_mode', 'max_combine', 'max_join',
                      'do_fit2']

        widget_list = list([self._widget_dict[par] for par in parameters])
        return widget_list

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

    def _clear_block_kwargs(self):
        """removes all block func kwarg widgets from the box"""
        parameters = ['max_combine', 'max_join', 'initial_block', 'block_size']
        for par in parameters:
            try:
                self.box_pop(par)
            except ValueError:
                pass

    @param.depends('block_mode', watch=True)
    def _update_block_mode(self):
        print('block mode updated')
        if self.block_mode == 'reduced':
            self._clear_block_kwargs()
            self.box_insert_after('block_mode', 'max_combine')
            self.box_insert_after('max_combine', 'max_join')
        elif self.block_mode == 'original':
            self._clear_block_kwargs()
        elif self.block_mode == 'constant':
            self._clear_block_kwargs()
            self.box_insert_after('block_mode', 'initial_block')
            self.box_insert_after('initial_block', 'block_size')


class FittingQuality(ControlPanel):
    header = 'Fitting Quality'

    peptide_index = param.Number(0, bounds=(0, None))
    x_axis_type = param.Selector(default='Log', objects=['Linear', 'Log'])
    chi_sq = param.Number(0., bounds=(0, None))

    def __init__(self, parent, **param):
        super(FittingQuality, self).__init__(parent, **param)

        self.parent.param.watch(self._series_updated, ['series'])

    def _series_updated(self, *events):

        self.param['peptide_index'].bounds =(0, len(self.parent.series.cov.data))


class ClassificationControl(ControlPanel):
    header = 'Classification'
    num_classes = param.Number(3, bounds=(1, 10), doc='Number of classification classes')
    target = param.Selector(label='Target')
    otsu_thd = param.Action(lambda self: self._action_threshold(), label='Otsu')
    show_thds = param.Boolean(True, label='Show Thresholds')
    values = param.List(precedence=-1)
    colors = param.List(precedence=-1)

    def __init__(self, parent, **param):
        super(ClassificationControl, self).__init__(parent, **param)

        self.values_widgets = []
        for _ in range(self.num_classes - 1):
            self._add_value()

        self.colors_widgets = []
        for _ in range(self.num_classes):
            self._add_color()

        self.param.trigger('values')
        self.param.trigger('colors')
        self.parent.param.watch(self._rates_updated, ['fit_results'])

    def make_dict(self):
        return self.generate_widgets(num_classes=pn.widgets.Spinner)

    def _rates_updated(self, *events):
        print('rates')
        print("UPDATE")

        objects = [k for k, v in self.parent.fit_results.items() if v['fitresult'] is not None]
        print(objects)
        self.param['target'].objects = objects

        #set target if its not set already
        if not self.target and objects:
            self.target = objects[-1]

    def _action_threshold(self):
        if self.num_classes > 1:
            rates = self.parent.fit_results[self.target]['rates']['rate']
            thd_rates = rates[~np.isnan(rates)]
            thds = threshold_multiotsu(np.log(thd_rates), classes=self.num_classes)
            for thd, widget in zip(thds, self.values_widgets):
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

        #todo make rates a property
        rates = self.parent.fit_results[self.target]['rates']['rate']
        #todo use function in support
        colors = np.empty(len(rates), dtype='U7')

        if self.num_classes == 1:
            colors[:] = self.colors[0]
        else:
            full_thds = [-np.inf] + self.values + [np.inf]
            for lower, upper, color in zip(full_thds[:-1], full_thds[1:], self.colors[::-1]):
                b = (rates > lower) & (rates <= upper)
                colors[b] = color

       # if 'color' in self.parent.rates.dtype.names:
        self.parent.rate_colors[self.target] = colors
        self.parent.param.trigger('rate_colors')

    @param.depends('num_classes', watch=True)
    def _update_num_colors(self):
        while len(self.colors_widgets) != self.num_classes:
            if len(self.colors_widgets) > self.num_classes:
                self._remove_color()
            elif len(self.colors_widgets) < self.num_classes:
                self._add_color()
        self.param.trigger('colors')

    @param.depends('num_classes', watch=True)
    def _update_num_values(self):
        while len(self.values_widgets) != self.num_classes - 1:
            if len(self.values_widgets) > self.num_classes - 1:
                self._remove_value()
            elif len(self.values_widgets) < self.num_classes - 1:
                self._add_value()
        self.param.trigger('values')

    def _add_value(self):
        default = 0.0
        self.values.append(default)

        name = 'Threshold {}'.format(len(self.values_widgets) + 1)
        widget = pn.widgets.LiteralInput(name=name, value=default)
        self.values_widgets.append(widget)
        i = len(self.values_widgets) + self.box_index('show_thds')
        self._box.insert(i, widget)
        widget.param.watch(self._value_event, ['value'])

    def _remove_value(self):
        widget = self.values_widgets.pop(-1)
        self.box_pop(widget)

        [widget.param.unwatch(watcher) for watcher in widget.param._watchers]
        del widget

    def _add_color(self):
        try:
            default = DEFAULT_CLASS_COLORS[len(self.colors_widgets)]
        except IndexError:
            default = '#FFFFFF'  #random color?

        self.colors.append(default)
        widget = pn.widgets.ColorPicker(value=default)
        self.colors_widgets.append(widget)
        i = len(self.values_widgets) + len(self.colors_widgets) + self.box_index('show_thds')
        self._box.insert(i, widget)
        widget.param.watch(self._color_event, ['value'])

    def _remove_color(self):
        widget = self.colors_widgets.pop(-1)
        self.box_pop(widget)
        [widget.param.unwatch(watcher) for watcher in widget.param._watchers]
        del widget

    #todo jslink?
    def _color_event(self, *events):
        print('color event')
        for event in events:
            print(event)
            idx = list(self.colors_widgets).index(event.obj)
            self.colors[idx] = event.new
            c_array = self.parent.rate_colors[self.target]
            c_array[c_array == event.old] = event.new
        self.param.trigger('colors')  # i dont think anyone listens to this
        self.parent.param.trigger('rate_colors')

    def _value_event(self, *events):
        for event in events:
            idx = list(self.values_widgets).index(event.obj)
            self.values[idx] = event.new
        self.param.trigger('values')


class FileExportPanel(ControlPanel):
    header = "File Export"
    target = param.Selector(label='Target')

    def __init__(self, parent, **param):
        super(FileExportPanel, self).__init__(parent, **param)
        self.parent.param.watch(self._rates_updated, ['fit_results'])

    def make_list(self):
        rates_export = pn.widgets.FileDownload(filename='Fit_rates.txt', callback=self.rates_export)
        data_export = pn.widgets.FileDownload(filename='Peptides.csv', callback=self.data_export)

        self._widget_dict.update(rates_export=rates_export, data_export=data_export)
        return super(FileExportPanel, self).make_list()

    def _rates_updated(self, *events):
        print('rates updated in fileexportpanel')
        #todo centralize this on parent? -> no child controls should hook into main controller
        objects = [k for k, v in self.parent.fit_results.items() if v['fitresult'] is not None]
        print(objects)
        self.param['target'].objects = objects
        #set target if its not set already
        if not self.target and objects:
            self.target = objects[-1]

    @pn.depends('target')
    def rates_export(self):
        io = StringIO()
        print(self.target)
        print('exporting')
        if self.target:
            fit_arr = self.parent.fit_results[self.target]['rates']
            if self.target in self.parent.rate_colors:
                colors = self.parent.rate_colors[self.target]
                export_data = append_fields(fit_arr, 'color', data=colors, usemask=False)
            else:
                export_data = fit_arr

            fmt, header = fmt_export(export_data)
            np.savetxt(io, export_data, fmt=fmt, header=header)

            io.seek(0)
            return io
        else:
            return None

    def data_export(self):
        io = StringIO()
        delimiter = ','

        #todo combine these lines into one function?
        fmt, header = fmt_export(self.parent.data, delimiter=delimiter, width=0)
        np.savetxt(io, self.parent.data, fmt=fmt, header=header, delimiter=delimiter)
        io.seek(0)
        return io


class OptionsPanel(ControlPanel):
    header = 'Options'

    """panel for various options and settings"""

    #todo this needs to access other panels as well

    link_xrange = param.Boolean(False)

    def __init__(self, parent, **param):
        super(OptionsPanel, self).__init__(parent, **param)
        self.cov_fig_panel = None
        self.rate_fig_panel = None
        self.coverage_ctrl = None

    #
    # def setup(self, fig1, fig2, coverage_ctrl):
    #     self.fig1 = fig1,
    #     self.fig2 = fig2

    @property
    def fig1(self):
        return self.cov_fig_panel.figures[0]

    @property
    def fig2(self):
        return self.rate_fig_panel.figure

    @property
    def enabled(self):
        return self.fig1 is not None and self.fig1 is not None and self.coverage_ctrl is not None

    @param.depends('link_xrange', watch=True)
    def _update_link(self):
        if self.enabled:
            if self.link_xrange:
                self._link()
            else:
                self._unlink()

    def _unlink(self):
        self.coverage_ctrl.param['aa_per_subplot'].constant = False
        self.fig1.x_range.js_property_callbacks.pop('change:start')
        self.fig1.x_range.js_property_callbacks.pop('change:end')

        self.fig2.x_range.js_property_callbacks.pop('change:start')
        self.fig2.x_range.js_property_callbacks.pop('change:end')

    def _link(self):
        step = 25  #todo global config
        value = int(step*(self.parent.series.cov.end // step + 1))
        self.coverage_ctrl.aa_per_subplot = value# triggers redraw
        self.coverage_ctrl.param['aa_per_subplot'].constant = True

        self.fig1.x_range.js_link('start', self.fig2.x_range, 'start')
        self.fig1.x_range.js_link('end', self.fig2.x_range, 'end')

        self.fig2.x_range.js_link('start', self.fig1.x_range, 'start')
        self.fig2.x_range.js_link('end', self.fig1.x_range, 'end')

    # def panel(self):
    #     return pn.WidgetBox(pn.Param(self.param))


class DeveloperPanel(ControlPanel):
    header = 'Developer Options'
    parse = param.Action(lambda self: self._action_load_files())

    def __init__(self, parent, **params):
        self.keys = ['fit1_rates', 'fit1_result', 'fit2_rates', 'fit2_result']
        self.file_selectors = {key: pn.widgets.FileInput() for key in self.keys}
        super(DeveloperPanel, self).__init__(parent, **params)

    def make_list(self):
        return list(self.file_selectors.values()) + [self._widget_dict['parse']]

    def _action_load_files(self):

        for k, fs in self.file_selectors.items():
            if fs.value is not None:
                name = k.split('_')[0]  # fit 1 or fit2
                if 'rates' in k:
                    s_io = StringIO(fs.value.decode('UTF-8'))
                    data = np_from_txt(s_io)
                    self.parent.fit_results[name]['rates'] = data
                elif 'result' in k:
                    b_io = BytesIO(fs.value)
                    result = pickle.load(b_io)
                    self.parent.fit_results[name]['fitresult'] = result
        self.parent.param.trigger('fit_results')

