import pathlib

from panel.template import GoldenTemplate
import panel as pn
import string


class ExtendedGoldenTemplate(GoldenTemplate):

    _template = pathlib.Path(__file__).parent / 'golden.html'

#    _css = pathlib.Path(__file__).parent / 'golden.css'

    # def _apply_root(self, name, model, tags):
    #     pass


class ReadString(str):
    """
    Extends the `string` class such that it can be used to monkey-patch the _template class attribute of GoldenTemplate
    """
    def read_text(self):
        return str(self)


class GoldenElvis(object):
    """
    Adaptation of Leon van Kouwen's elvis layout system
    https://github.com/LeonvanKouwen/elvis

    Generates a jinja GoldenLayout Template based on panel's default GoldenLayout Template. This modification features a
    fixed sidebar with a main layout part which can be customized with columns/rows/stacks

    """

    NESTABLE = \
        """
        {
            type: '%s',
            content: [ %s ]
        },
        """

    VIEW = \
        """
        {   
            type: 'component',
            componentName: 'view',
            componentState: 
            { 
                model: '{{ embed(roots.%s) }}',
                %s
            },
            isClosable: false,
        },
        """

    def __init__(self, template, theme, title=None):
        self.template_cls = template
        self.theme_cls = theme
        self.title = title

        self.panels = {}
        #self.template = template(title=title, theme=theme)

    @property
    def jinja_base_string_template(self):
        _base = pathlib.Path(__file__).parent / 'jinja_base.html'
        base_string_template = string.Template(_base.read_text())

        return base_string_template

    def compose(self, controllers, golden_layout_string):
        """
        Creates a servable template from a golden layout js code string.
        :param golden_layout_string: Result of nesting stacks, columns, rows, and panels
                                     using the methods in this class.
        """

        template_code = ReadString(self.jinja_base_string_template.substitute(main_body=golden_layout_string))
        self.template_cls._template = template_code

        template = self.template_cls(title=self.title, theme=self.theme_cls)
        controls = pn.Column(*[controller.panel for controller in controllers])

        template.sidebar.append(controls)

        for panel_ID, panel in self.panels.items():
            template._render_items[panel_ID] = (panel, ['main'])

        return template

    def view(self, view, title=None, width=None, height=None, scrollable=True):
        """
        Adds a viewable panel.
        :param view: The panel to show in this golden layout sub section.
        :param title: The text to show at the top of the panel.
        :param width: Initial width.
        :param height: Initial height.
        """

        # We need to register every panel with a unique name such that after
        # composing the jinja2 template, we can add them (see compose function).

        # It seems that these unique names cannot start with a number or they cannot be referenced directly
        # Therefore, currently tmpl.main.append cannot be used as this generates
        panel_ID = 'ID' + str(id(view))
        print('title, id', title, panel_ID)

        self.panels[panel_ID] = view
        title_str = "title: '%s'," % str(title) if title is not None else "title: '',"
        width_str = "width: %s," % str(width) if width is not None else ""
        height_str = "height: %s," % str(height) if height is not None else ""
        scroll_str = "css_classes: ['not_scrollable']" if not scrollable else ""
        settings = title_str + height_str + width_str + scroll_str
        return self.VIEW % (panel_ID, settings)

    def _block(self, *args, type='stack'):
        """
        Creates nestable js code strings. Note that 'stack', 'colum' and 'row' are the
        strings dictated by the golden layout js code.
        """
        content = ''.join(arg for arg in args)
        return self.NESTABLE % (type, content)

    def stack(self, *args):
        """ Adds a 'tab' element."""
        return self._block(*args, type='stack')

    def column(self, *args):
        """ Vertically aligned panels"""
        return self._block(*args, type='column')

    def row(self, *args):
        """ Horizontally aligned panels"""
        return self._block(*args, type='row')