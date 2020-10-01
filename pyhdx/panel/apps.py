from pyhdx.panel.template import GoldenElvis, ExtendedGoldenTemplate
from pyhdx.panel.theme import ExtendedGoldenDarkTheme, ExtendedGoldenDefaultTheme
from pyhdx.panel.controllers import *
from pyhdx.panel.main_controllers import ComparisonController, PyHDXController
from pyhdx.panel.fig_panels import *
from pyhdx.panel.log import get_default_handler
import sys
from pyhdx import VERSION_STRING_SHORT
from holoviews import Bivariate
DEBUG = False
cluster = '127.0.0.1:52123'


def main_app():
    control_panels = [
        PeptideFileInputControl,
        CoverageControl,
        InitialGuessControl,
        FitControl,
        FitResultControl,
        ClassificationControl,
        FileExportControl,
        ProteinViewControl,
        OptionsControl
    ]

    if DEBUG:
        control_panels.append(DeveloperControl)

    figure_panels = [
        CoverageFigure,
        RateFigure,
        PFactFigure,
        FitResultFigure,
        ProteinFigure,
        LoggingFigure
    ]

    elvis = GoldenElvis(ExtendedGoldenTemplate, ExtendedGoldenDarkTheme, title=VERSION_STRING_SHORT)
    ctrl = PyHDXController(control_panels, figure_panels, cluster=cluster)
    ctrl.logger.addHandler(get_default_handler(sys.stdout))
    tmpl = elvis.compose(ctrl,
                         elvis.column(
                             elvis.stack(
                                 elvis.view(ctrl.figure_panels['CoverageFigure']),
                                 elvis.view(ctrl.figure_panels['ProteinFigure'])
                             ),
                             elvis.stack(
                                 elvis.view(ctrl.figure_panels['RateFigure']),
                                 elvis.view(ctrl.figure_panels['PFactFigure']),
                                 elvis.view(ctrl.figure_panels['FitResultFigure']),
                                 elvis.view(ctrl.figure_panels['LoggingFigure']),
                             )
                         ))

    ctrl.control_panels['OptionsControl']._update_link()
    return tmpl


def single_app():
    control_panels = [
        MappingFileInputControl,
        SingleControl,
        ClassificationControl,
        ProteinViewControl,
        DifferenceFileExportControl,
        OptionsControl,
        DeveloperControl
    ]

    if DEBUG:
        control_panels.append('DeveloperControl')

    figure_panels = [
        BinaryComparisonFigure,
        ProteinFigure,
        LoggingFigure
    ]

    elvis = GoldenElvis(ExtendedGoldenTemplate, ExtendedGoldenDarkTheme, title=VERSION_STRING_SHORT)
    ctrl = ComparisonController(control_panels, figure_panels, cluster=cluster)
    ctrl.logger.addHandler(get_default_handler(sys.stdout))
    tmpl = elvis.compose(ctrl,
                         elvis.column(
                             elvis.stack(
                                 elvis.view(ctrl.figure_panels['ProteinFigure'])
                             ),
                             elvis.row(
                                 elvis.stack(
                                    elvis.view(ctrl.figure_panels['BinaryComparisonFigure']),
                                 ),
                                 elvis.view(ctrl.figure_panels['LoggingFigure']),
                             )
                         ))

    ctrl.control_panels['ClassificationControl'].log_space = False

    return tmpl


def diff_app():
    control_panels = [
        MappingFileInputControl,
        DifferenceControl,
        ClassificationControl,
        ProteinViewControl,
        DifferenceFileExportControl,
        OptionsControl,
        DeveloperControl
    ]

    if DEBUG:
        control_panels.append('DeveloperControl')

    figure_panels = [
        BinaryComparisonFigure,
        SingleValueFigure,
        ProteinFigure,
        LoggingFigure
    ]

    elvis = GoldenElvis(ExtendedGoldenTemplate, ExtendedGoldenDarkTheme, title=VERSION_STRING_SHORT)
    ctrl = ComparisonController(control_panels, figure_panels, cluster=cluster)
    ctrl.logger.addHandler(get_default_handler(sys.stdout))
    tmpl = elvis.compose(ctrl,
                         elvis.column(
                             elvis.stack(
                                 elvis.view(ctrl.figure_panels['ProteinFigure'])
                             ),
                             elvis.row(
                                 elvis.stack(
                                    elvis.view(ctrl.figure_panels['BinaryComparisonFigure']),
                                    elvis.view(ctrl.figure_panels['SingleValueFigure'])
                                 ),
                                 elvis.view(ctrl.figure_panels['LoggingFigure']),
                             )
                         ))

    ctrl.control_panels['ClassificationControl'].log_space = False
    return tmpl