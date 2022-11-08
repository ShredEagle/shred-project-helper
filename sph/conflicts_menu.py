from py_cui import widgets
import pdb

from sph.choice import Choice

class ConflictsMenu(widgets.ScrollMenu):
    def __init__(self, id, title, grid, row, column, row_span, column_span, padx, pady, logger):
        super().__init__(id, title, grid, row, column, row_span, column_span, padx, pady, logger)
        self._selected_item = self.get_next_dependency_index()

    def add_item_list(self, item_list):
        super().add_item_list(item_list)
        if len(self.get_item_list()) == len(item_list):
            self._selected_item = self.get_next_dependency_index()

    def get_previous_dependency_index(self):
        current_index = self.get_selected_item_index() - 1
        find_index = -1

        while find_index == -1 and current_index > 0:
            if isinstance(self._view_items[current_index], Choice):
                find_index = current_index
            else:
                current_index -= 1

        if find_index != -1:
            return find_index

        return self.get_selected_item_index()

    def get_next_dependency_index(self):
        current_index = self.get_selected_item_index() + 1
        find_index = -1

        while find_index == -1 and current_index < len(self.get_item_list()):
            if isinstance(self._view_items[current_index], Choice):
                find_index = current_index
            else:
                current_index += 1

        if find_index != -1:
            return find_index

        return self.get_selected_item_index()


    def _scroll_up(self):
        new_index = self.get_previous_dependency_index()

        if self._top_view > 0 and self._selected_item == self._top_view:
            self._top_view = new_index

        if self._selected_item > 0:
            self._selected_item = new_index

        self._logger.debug(f'Scrolling up to item {self._selected_item}') 

    def _scroll_down(self, viewport_height: int):
        new_index = self.get_next_dependency_index()

        if self._selected_item < len(self._view_items) - 1:
            self._selected_item = new_index
        if self._selected_item > self._top_view + viewport_height:
            self._top_view =  new_index
 
        self._logger.debug(f'Scrolling down to item {self._selected_item}') 
