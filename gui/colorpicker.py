# This file is part of MyPaint.
# Copyright (C) 2009-2012 by Martin Renold <martinxyz@gmx.ch>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

import math
import pygtkcompat
import gobject
import gtk
from gtk import gdk
import windowing
import cairo
import canvasevent
import linemode
from overlays import rounded_box, Overlay
import colors


class ColorPickMode (canvasevent.SpringLoadedDragMode,
                     canvasevent.OneshotDragModeMixin):
    """Mode for picking colors from the screen, with a preview.
    """

    # Class configuration
    __action_name__ = 'ColorPickMode'
    PICK_SIZE = 6

    # Keyboard activation behaviour (instance defaults)
    # See keyboard.py and doc.mode_flip_action_activated_cb()
    keyup_timeout = 0


    @property
    def inactive_cursor(self):
        return self.doc.app.cursor_color_picker


    def stackable_on(self, mode):
        # Any drawing mode
        return isinstance(mode, linemode.LineModeBase) \
            or isinstance(mode, canvasevent.SwitchableFreehandMode)


    def __init__(self, **kwds):
        super(ColorPickMode, self).__init__(**kwds)
        self._overlay = None
        self._preview_needs_button_press = 'ignore_modifiers' not in kwds
        self._button_press_seen = False


    def enter(self, **kwds):
        """Enters the mode, starting the grab immediately.
        """
        super(ColorPickMode, self).enter(**kwds)
        if self._picking():
            self.doc.app.pick_color_at_pointer(self.doc.tdw, self.PICK_SIZE)
        self._force_drag_start()


    def leave(self, **kwds):
        if self._overlay is not None:
            self._overlay.cleanup()
            self._overlay = None
        super(ColorPickMode, self).leave(**kwds)


    def button_press_cb(self, tdw, event):
        self._button_press_seen = True
        self.doc.app.pick_color_at_pointer(self.doc.tdw, self.PICK_SIZE)
        return super(ColorPickMode, self).button_press_cb(tdw, event)


    def drag_stop_cb(self):
        if self._overlay is not None:
            self._overlay.cleanup()
            self._overlay = None
        super(ColorPickMode, self).drag_stop_cb()


    def _picking(self):
        return not (self._preview_needs_button_press
                    and not self._button_press_seen)


    def drag_update_cb(self, tdw, event, dx, dy):
        picking = self._picking()
        if picking:
            self.doc.app.pick_color_at_pointer(tdw, self.PICK_SIZE)
            if self._overlay is None:
                self._overlay = ColorPickPreviewOverlay(self.doc, tdw,
                                                        event.x, event.y)
        if self._overlay is not None:
            self._overlay.move(event.x, event.y)
        return super(ColorPickMode, self).drag_update_cb(tdw, event, dx, dy)



class ColorPickPreviewOverlay (Overlay):
    """Preview overlay during color picker mode.
    """

    PREVIEW_SIZE = 70
    OUTLINE_WIDTH = 3
    CORNER_RADIUS = 10


    def __init__(self, doc, tdw, x, y):
        """Initialize, attaching to the brush and to the tdw.

        Observer callbacks and canvas overlays are registered by this
        constructor, so cleanup() must be called when the owning mode leave()s.

        """
        self._doc = doc
        self._tdw = tdw
        self._x = int(x)+0.5
        self._y = int(y)+0.5
        alloc = tdw.get_allocation()
        self._tdw_w = alloc.width
        self._tdw_h = alloc.height
        self._color = self._get_app_brush_color()
        app = doc.app
        app.brush.observers.append(self._brush_color_changed_cb)
        tdw.display_overlays.append(self)
        self._previous_area = None
        self._queue_tdw_redraw()


    def cleanup(self):
        """Cleans up temporary observer stuff, allowing garbage collection.
        """
        app = self._doc.app
        app.brush.observers.remove(self._brush_color_changed_cb)
        self._tdw.display_overlays.remove(self)
        assert self._brush_color_changed_cb not in app.brush.observers
        assert self not in self._tdw.display_overlays
        self._queue_tdw_redraw()


    def move(self, x, y):
        """Moves the preview square to a new location, in tdw pointer coords.
        """
        self._x = int(x)+0.5
        self._y = int(y)+0.5
        self._queue_tdw_redraw()


    def _get_app_brush_color(self):
        app = self._doc.app
        return colors.HSVColor(*app.brush.get_color_hsv())


    def _brush_color_changed_cb(self, settings):
        if not settings.intersection(('color_h', 'color_s', 'color_v')):
            return
        self._color = self._get_app_brush_color()
        self._queue_tdw_redraw()


    def _queue_tdw_redraw(self):
        if self._previous_area is not None:
            self._tdw.queue_draw_area(*self._previous_area)
            self._previous_area = None
        area = self._get_area()
        if area is not None:
            self._tdw.queue_draw_area(*area)


    def _get_area(self):
        # Returns the drawing area for the square
        size = self.PREVIEW_SIZE

        # Start with the pointer location
        x = self._x
        y = self._y

        offset = size // 2

        # Only show if the pointer is inside the tdw
        alloc = self._tdw.get_allocation()
        if x < 0 or y < 0 or y > alloc.height or x > alloc.width:
            return None

        # Convert to preview location
        # Pick a direction - N,W,E,S - in which to offset the preview
        if y + size > alloc.height - offset:
            x -= offset
            y -= size + offset
        elif x < offset:
            x += offset
            y -= offset
        elif x > alloc.width - offset:
            x -= size + offset
            y -= offset
        else:
            x -= offset
            y += offset

        ## Correct to place within the tdw
        #if x < 0:
        #    x = 0
        #if y < 0:
        #    y = 0
        #if x + size > alloc.width:
        #    x = alloc.width - size
        #if y + size > alloc.height:
        #    y = alloc.height - size

        return (int(x), int(y), size, size)


    def paint(self, cr):
        area = self._get_area()
        if area is not None:
            x, y, w, h = area
            size = self.PREVIEW_SIZE

            cr.set_source_rgb(*self._color.get_rgb())
            x += (self.OUTLINE_WIDTH // 2) + 1.5
            y += (self.OUTLINE_WIDTH // 2) + 1.5
            w -= self.OUTLINE_WIDTH + 3
            h -= self.OUTLINE_WIDTH + 3
            rounded_box(cr, x, y, w, h, self.CORNER_RADIUS)
            cr.fill_preserve()

            cr.set_source_rgb(0, 0, 0)
            cr.set_line_width(self.OUTLINE_WIDTH)
            cr.stroke()

        self._previous_area = area

