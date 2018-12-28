# -*- coding: utf-8 -*-
#
# Copyright (C) 2014-2018 Bitergia
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
#
# Authors:
#   Valerio Cosentino <valcos@bitergia.com>
#

import logging
import json
import os
from pathlib import Path

from archimedes.kibana import Kibana
from archimedes.clients.dashboard import (DASHBOARD,
                                          INDEX_PATTERN,
                                          SEARCH,
                                          VISUALIZATION)
from archimedes.errors import ExportError, FileTypeError, ObjectTypeError
from archimedes.utils import (find_file,
                              load_json,
                              save_to_file)

VISUALIZATIONS_FOLDER = 'visualizations'
INDEX_PATTERNS_FOLDER = 'index-patterns'
SEARCHES_FOLDER = 'searches'

JSON_EXT = '.json'

logger = logging.getLogger(__name__)


def get_file_name(obj_type, obj_id):
    """Build the name of a file according the object type and ID.

    :param obj_type: type of the object
    :param obj_id: ID of the object
    """
    name = obj_type + '_' + obj_id + JSON_EXT
    return name.lower()


def get_folder_path(root_path, obj_type):
    """Build the path of a folder according to the object type.

    :param root_path: root path
    :param obj_type: type of the object
    """
    name = ''
    folder_path = root_path

    if obj_type == VISUALIZATION:
        name = VISUALIZATIONS_FOLDER
    elif obj_type == INDEX_PATTERN:
        name = INDEX_PATTERNS_FOLDER
    elif obj_type == SEARCH:
        name = SEARCHES_FOLDER

    if name:
        folder_path = os.path.join(root_path, name)

    os.makedirs(folder_path, exist_ok=True)
    return folder_path


class Archimedes:
    """This class allows the import and export objects such as
    dashboards, visualizations, searches and index patterns to
    and from a Kibana instance.

    ::param url: the Kibana URL
    """
    def __init__(self, url):
        self.url = url
        self.kibana = Kibana(url)

    def import_from_file(self, file_path, find=False, visualizations_folder=None, searches_folder=None,
                         index_patterns_folder=None, force=False):
        """Import Kibana objects from a JSON file. If `search` is set to true, it also loads the related objects
        (i.e., visualizations, search and index pattern) located in different folders.

        The method can overwrite previous versions of existing objects by setting
        the parameter `force` to true.

        :param file_path: path of the target file
        :param find: find the objects referenced in the file
        :param visualizations_folder: folder where visualization objects are stored
        :param searches_folder: folder where search objects are stored
        :param index_patterns_folder: folder where index pattern objects are stored
        :param force: overwrite any existing objects on ID conflict
        """
        json_content = load_json(file_path)

        if not json_content:
            logger.warning("File %s is empty", file_path)
            return

        if not find:
            self.__import_file(file_path, force)
            return

        file_type = Path(file_path).name.split("_")[0].lower()

        if file_type == DASHBOARD:
            files = self._find_dashboard_files(file_path, visualizations_folder,
                                               searches_folder, index_patterns_folder)
        elif file_type == VISUALIZATION:
            files = self._find_visualization_files(file_path, searches_folder, index_patterns_folder)
        elif file_type == SEARCH:
            files = self._find_search_files(file_path, index_patterns_folder)
        else:
            cause = "File type %s not known" % file_type
            logger.error(cause)
            raise FileTypeError(cause=cause)

        self.__import_files(files, force=force)

    def export(self, obj_type, folder_path, obj_id=None, obj_title=None, one_file=False, force=False, index_pattern=False):
        """Locate an object based on its type and ID or title in Kibana and export it to a `folder_path`.
        The exported data can be saved in a single file (`one_file` = True) or divided into several folders
        according to the type of the objects exported (i.e., visualizations, searches and index patterns).

        The method can overwrite previous versions of existing files by setting the
        parameter `force` to true.

        :param obj_type: type of the target object
        :param obj_id: ID of the target object
        :param obj_title: title of the target object
        :param folder_path: folder where to export the dashboard objects
        :param one_file: export the dashboard objects to a file
        :param force: overwrite an existing file on file name conflict
        :param index_pattern: export also the index pattern
        """
        if obj_id:
            obj = self.kibana.export_by_id(obj_type, obj_id)
        elif obj_title:
            obj = self.kibana.export_by_title(obj_type, obj_title)
        else:
            cause = "Object id and title cannot be null"
            logger.error(cause)
            raise ExportError(cause=cause)

        self.__export_objects(obj, obj_type, folder_path, one_file, force, index_pattern)

    def _find_dashboard_files(self, dashboard_path, visualizations_folder=None,
                              searches_folder=None, index_patterns_folder=None):
        """Find the files containing the objects referenced in `dashboard_path`
        by looking into `visualizations_folder`, `searches_folder` and
        `index_patterns_folder`.

        :param dashboard_path: path of the dashboard to import
        :param visualizations_folder: folder where visualization objects are stored
        :param searches_folder: folder where searches objects are stored
        :param index_patterns_folder: folder where index pattern objects are stored

        :returns the list of files containing the objects that compose a dashboard
        """
        dashboard_files = []
        dash_content = load_json(dashboard_path)

        if not visualizations_folder:
            logger.info("Visualizations not loaded for %s, visualizations folder not set", dashboard_path)
            dashboard_files.append(dashboard_path)
            return dashboard_files

        panels = json.loads(dash_content['attributes']['panelsJSON'])
        for panel in panels:
            if panel['type'] == VISUALIZATION:
                panel_path = find_file(visualizations_folder, get_file_name(VISUALIZATION, panel['id']))
                panel_files = self._find_visualization_files(panel_path, searches_folder, index_patterns_folder)
            elif panel['type'] == SEARCH:
                panel_path = find_file(searches_folder, get_file_name(SEARCH, panel['id']))
                panel_files = self._find_search_files(panel_path, index_patterns_folder)
            else:
                cause = "Panel type %s not handled" % (panel['type'])
                logger.error(cause)
                raise ObjectTypeError(cause=cause)

            [dashboard_files.append(p) for p in panel_files if p not in dashboard_files]

        dashboard_files.append(dashboard_path)

        return dashboard_files

    def _find_visualization_files(self, visualization_path, searches_folder=None, index_patterns_folder=None):
        """Find the files containing the objects referenced in `visualization_path`
        by looking into `searches_folder` and `index_patterns_folder`.

        :param visualization_path: path of the visualization to import
        :param searches_folder: folder where searches objects are stored
        :param index_patterns_folder: folder where index pattern objects are stored

        :returns the list of files containing the objects that compose a visualization
        """
        visualization_files = []
        vis_content = load_json(visualization_path)

        if not searches_folder:
            logger.info("Searches won't be loaded for %s, searches folder not set", searches_folder)

        if not index_patterns_folder:
            logger.info("Index patterns won't be loaded %s, index patterns folder not set", index_patterns_folder)

        if 'savedSearchId' in vis_content['attributes'] and searches_folder:
            search_id = vis_content['attributes']['savedSearchId']
            search_path = find_file(searches_folder, get_file_name(SEARCH, search_id))
            if search_path not in visualization_files:
                visualization_files.append(search_path)

        search_files = self._find_search_files(visualization_path, index_patterns_folder)
        [visualization_files.append(sf) for sf in search_files if sf not in visualization_files]

        return visualization_files

    def _find_search_files(self, search_path, index_patterns_folder=None):
        """Find the files containing the objects referenced in `search_path`
        by looking into `index_patterns_folder`.

        :param index_patterns_folder: folder where index pattern objects are stored

        :returns the list of files containing the objects that compose a search
        """
        search_files = []
        search_content = load_json(search_path)

        index_pattern_id = self.__find_index_pattern(search_content)
        if not index_pattern_id:
            logger.info("No index pattern declared for search %s", search_path)
            search_files.append(search_path)
            return search_files

        ip_path = find_file(index_patterns_folder, get_file_name(INDEX_PATTERN, index_pattern_id))
        if ip_path not in search_files:
            search_files.append(ip_path)

        search_files.append(search_path)

        return search_files

    def __find_index_pattern(self, obj):
        """Find the index pattern id in an `obj`.

        :param obj: Kibana object

        :returns the index pattern id
        """
        index_pattern = None
        if 'kibanaSavedObjectMeta' in obj['attributes'] \
                and 'searchSourceJSON' in obj['attributes']['kibanaSavedObjectMeta']:
            search_content = json.loads(obj['attributes']['kibanaSavedObjectMeta']['searchSourceJSON'])
            if 'index' not in search_content:
                return index_pattern

            index_pattern = search_content['index']

        return index_pattern

    def __import_files(self, file_paths, force=False):
        """Import dashboards, index patterns, visualizations and searches from a list of JSON files to Kibana.
        Each JSON file should be either a list of objects or a dict having a key 'objects'
        with a list of objects as value (e.g,, {'objects': [...]}.

        The method can overwrite previous versions of existing objects by setting
        the parameter `force` to true.

        :param file_paths: target file paths
        :param force: overwrite any existing objects on ID conflict
        """
        logger.info("Importing %s files", len(file_paths))
        for f in file_paths:
            self.__import_file(f, force=force)

    def __import_file(self, file_path, force=False):
        """Import dashboards, index patterns, visualizations and searches from a JSON file to Kibana.
        The JSON file should be either a list of objects or a dict having a key 'objects'
        with a list of objects as value (e.g,, {'objects': [...]}.

        The method can overwrite previous versions of existing objects by setting
        the parameter `force` to true.

        :param file_path: path of the target file
        :param force: overwrite any existing objects on ID conflict
        """
        json_content = load_json(file_path)

        if not json_content:
            logger.warning("File %s is empty", file_path)
            return

        if 'objects' not in json_content:
            objects = {'objects': [json_content]}
        else:
            objects = json_content

        kibana = Kibana(self.url)
        logger.info("Importing %s", file_path)
        kibana.import_objects(objects, force)

    def __export_objects(self, data, obj_type, folder_path, one_file, force, index_pattern=False):
        """Export Kibana objects to a `folder_path`. The exported data
        can be saved in a single file (`one_file` = True) or divided into several folders
        according to the type of the objects exported (e.g., visualizations, searches
        and index patterns).

        The method can overwrite previous versions of existing files by setting the
        parameter `force` to true.

        :param data: data to export (it can be a single object or a list)
        :param obj_type: type of the target object
        :param folder_path: folder where to export the dashboard objects
        :param one_file: export the dashboard objects to a file
        :param force: overwrite an existing file on file name conflict
        :param index_pattern: export also the index pattern
        """
        if one_file and obj_type == DASHBOARD:
            logger.info("Exporting to one file to folder %s", folder_path)
            dash = [obj for obj in data['objects'] if obj['type'] == 'dashboard'][0]
            file_path = os.path.join(folder_path, get_file_name(dash['type'], dash['id']))
            save_to_file(data, file_path, force)
            return

        if 'objects' not in data:
            objs = [data]
        else:
            objs = data['objects']

        for obj in objs:
            folder = get_folder_path(folder_path, obj['type'])
            file_path = os.path.join(folder, get_file_name(obj['type'], obj['id']))
            save_to_file(obj, file_path, force)

            if index_pattern:
                index_pattern_id = self.__find_index_pattern(obj)
                index_pattern_obj = self.kibana.find_by_id(INDEX_PATTERN, index_pattern_id)
                folder = get_folder_path(folder_path, INDEX_PATTERN)
                file_path = os.path.join(folder, get_file_name(INDEX_PATTERN, index_pattern_id))
                save_to_file(index_pattern_obj, file_path, force)