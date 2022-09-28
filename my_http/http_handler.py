import re

from my_http.http_constants.http_methods import HTTP_METHODS_AS_LIST
from my_http.http_constants.response_codes import BAD_REQUEST, HTTP_VERSION_NOT_SUPPORTED
from my_http.data_types import HttpRequest, _HttpResponse, HttpResponse
from my_socketserver import BaseRequestHandler
from config import ENCODING

class BaseController():
    def __init__(self, base_path=""):
        self.methods_list = self._get_methods_list()

        self.methods_dict = dict()
        for method in self.methods_list:
            self.methods_dict[method] = base_path
        
        self._validate_http_methods_notation()


    def _get_methods_list(self):
        pattern = re.compile("^__.*__$")
        base_controller_methods_list = list(filter(lambda x:(pattern.match(x) == None) , dir(BaseController)))
        methods_list = list(filter(lambda x:(pattern.match(x) == None and x not in base_controller_methods_list) , dir(self)))
        return methods_list


    def _validate_http_methods_notation(self):
        for method in self.methods_dict:
            if method.split("_")[0] not in HTTP_METHODS_AS_LIST:
                raise ValueError(f" \"{method}\" method from controller: \"{self.__class__.__name__}\" should have one of {HTTP_METHODS_AS_LIST} at the begging of name, delimited with an underscore.")


    def _validate_methods_dict(self):        
        for method in self.methods_list:
            try:
                self.methods_dict[method]
            except KeyError:
                raise ValueError(f"Method \"{method}\" does not have a path set in controller \"{self.__class__.__name__}\" initialization.")

        for method, path in self.methods_dict.items():
            if method not in self.methods_list:
                raise ValueError(f"Method \"{method}\" declared in controller \"{self.__class__.__name__}\" initialization, does not exist")

    def _regex_escape(string):
        regex_special_chars_map = {chr(i): '\\' + chr(i) for i in b'()[]{}?*+-|^$\\.&~# \t\n\r\v\f'}
        aux = ""
        for ch in string:
            if ch in regex_special_chars_map:
                aux += regex_special_chars_map[ch]
            else:
                aux += ch
        return aux

    def _match_path(pattern_path, path):
        pattern_path = BaseController._regex_escape(pattern_path)  
        pattern = re.compile("\\\{[^{}]*}")
        uncompiled_pattern_string = re.sub(pattern, ".*", pattern_path)
        pattern = re.compile(uncompiled_pattern_string)

        return pattern.match(path)


    def _validate_paths(self, other_controllers):
        def validate_the_2_paths_for_ambiguity(method, path, other_controller, other_method, other_path):
            if BaseController._match_path(path, other_path) is not None:
                comprehensive_error_dict = {"controller" : self.__class__.__name__, "method" : method, "path" : path}
                comprehensive_error_dict_other = {"controller" : other_controller.__class__.__name__, "method" : other_method, "path" : other_path}
                raise ValueError(f"Path ambiguity detected between: {comprehensive_error_dict} and {comprehensive_error_dict_other}")

        for idx, (method, path) in enumerate(self.methods_dict.items()):
            for other_method, other_path in list(self.methods_dict.items())[:idx] + list(self.methods_dict.items())[idx + 1:]:
                validate_the_2_paths_for_ambiguity(method, path, self, other_method, other_path)

            for other_controller in other_controllers:
                for other_method, other_path in other_controller.methods_dict.items():
                    validate_the_2_paths_for_ambiguity(method, path, other_controller, other_method, other_path)



    def _reverse_string(string):
        stack = list()
        for elem in string:
            stack.append(elem)
        string = ""
        while stack:
            string += stack.pop()
        return string

    def _compute_path_without_request_param_string(path):
            path = BaseController._reverse_string(path)
            path = path.split("?", 1)[0]
            path = BaseController._reverse_string(path)
            return path


    def _compute_request_param_string(path):
            path = BaseController._reverse_string(path)
            path = path.split("?", 1)[1]
            path = BaseController._reverse_string(path)
            return path


    def _find_implementation(self, path):
        path = BaseController._compute_path_without_request_param_string(path)
        for method, stored_path in self.methods_dict.items():
            if BaseController._match_path(stored_path, path):
                return method
        return None



    def _compute_ordered_list_of_keywords(path):
        pattern = re.compile("{[^{}]*}")
        ordered_list_of_keywords = list()
        current_key = pattern.search(path)
        if current_key is not None:
            ordered_list_of_keywords.append(current_key.group(0)[1:-1])
        slice = path
        while current_key is not None:
            slice = slice[current_key.end():]
            current_key = pattern.search(slice)
            if current_key is not None:
                ordered_list_of_keywords.append(current_key.group(0)[1:-1])
        return ordered_list_of_keywords


    def _compute_ordered_lists_of_keywords_starts_and_ends(path):
        pattern = re.compile("{[^{}]*}")
        offset = 0
        ordered_list_of_keywords_starts = list()
        ordered_list_of_keywords_ends = list()
        current_key = pattern.search(path)
        if current_key is not None:
            ordered_list_of_keywords_starts.append(current_key.start())
            ordered_list_of_keywords_ends.append(current_key.end())
            offset = current_key.end()
        while current_key is not None:
            slice = path[offset:]
            current_key = pattern.search(slice)
            if current_key is not None:
                ordered_list_of_keywords_starts.append(current_key.start() + offset)
                ordered_list_of_keywords_ends.append(current_key.end() + offset)
                offset+= current_key.end()
        return ordered_list_of_keywords_starts, ordered_list_of_keywords_ends



    def _compute_ordered_list_of_values(path, stored_path):
        ordered_list_of_keywords_starts, ordered_list_of_keywords_ends = BaseController._compute_ordered_lists_of_keywords_starts_and_ends(stored_path)

        idx_path = ordered_list_of_keywords_starts[0]
        ordered_list_of_values = list()
        slice = path
        for (idx_s, keyword_start), keyword_end in zip(enumerate(ordered_list_of_keywords_starts), ordered_list_of_keywords_ends):
            value = ""
            last_slice = slice
            while BaseController._match_path(stored_path[keyword_start:], slice) is not None and last_slice != "":
                if idx_path < len(path):
                    value += path[idx_path]
                idx_path += 1
                last_slice = slice
                slice = path[idx_path:]
            if idx_path < len(path):
                value = value[:-1]
            ordered_list_of_values.append(value)
            
            if idx_s + 1 < len(ordered_list_of_keywords_starts):
                if len(value) > 0:
                    idx_path += ordered_list_of_keywords_starts[idx_s + 1] - keyword_end - 1
                else:
                    idx_path += ordered_list_of_keywords_starts[idx_s + 1] - keyword_end
        return ordered_list_of_values


    def get_path_variables(self, path):
        stored_path = self.methods_dict[self._find_implementation(path)]   #Can be implemented more efficiently with getting caller name or passing a parameter
        path = BaseController._compute_path_without_request_param_string(path)
        ordered_list_of_keywords = BaseController._compute_ordered_list_of_keywords(stored_path)
        ordered_list_of_values = BaseController._compute_ordered_list_of_values(path, stored_path)
        path_variables = dict()
        for key, value in zip(ordered_list_of_keywords, ordered_list_of_values):
            path_variables[key] = value
        return path_variables



    #TODO
    def get_query_param(self, path):
        pass


class HttpHandler(BaseRequestHandler):
    def __init__(self, request, client_address, server, controller_manager):
        self.controller_manager = controller_manager
        self.HTTP_VERSION = "HTTP/1.1"
        super().__init__(request, client_address, server)

    def handle(self):
        data = ""
        while True:
            data += str(self.request.recv(1024), ENCODING)
            if HttpHandler.check_if_all_data_is_recieved(data) is True:
                break

        valid_request = True
        try:
            http_request = self.decode_data(data)
        except IndexError:
            valid_request = False

        if valid_request is True:
            if http_request.http_version != self.HTTP_VERSION:
                valid_request = False

        if valid_request:
            response = self.find_implementation_and_execute(http_request)
            response = _HttpResponse(self.HTTP_VERSION, response.status_code, response.headers, response.body)

        else:
            status = HTTP_VERSION_NOT_SUPPORTED
            headers = {"Content-Length": str(0)}
            body = ""
            response = _HttpResponse(status, headers, body, self.HTTP_VERSION)
        
        a = response.make_response_string()
        self.request.send(response.make_response_string())


    def check_if_all_data_is_recieved(data):
        if data == "" or data is None:
            return False

        if len(data.split("\r\n\r\n")) == 1:
            return False

        body_length = None
        for line in data.split("\r\n\r\n")[0].split("\r\n"):
            if "Content-Length" in line:
                line = line.split(":")
                body_length = int(line[1])
        
        method = data.split("\r\n")[0].split(" ")[0]
        if body_length is None and method != "GET":
            return False

        if body_length is None and method == "GET":
            return True
        
        if len(data.split("\r\n\r\n")[1]) == body_length:
            return True


    def decode_data(self, data):
        http_method = None
        route_mapping = None
        http_version = None
        headers = dict()
        body = None

        data = data.split("\r\n")

        http_method = data[0].split(" ")[0]
        route_mapping = data[0].split(" ")[1]
        http_version = data[0].split(" ")[2]
        
        headers_portion = list()
        for idx, line in enumerate(data):
            if line == "":
                headers_portion = data[1:idx]
                body = data[idx+1:]
                break
        
        aux = body
        body = ""
        for line in aux:
            body += line + "\r\n"
        body = body[:-2]

        for line in headers_portion:
            line = line.split(": ")
            headers[line[0]] = line[1]

        return HttpRequest(http_method, route_mapping, http_version, headers, body, self.client_address, self.server)


    def find_implementation_and_execute(self, http_request):
        result = self.controller_manager.find_implementation_and_execute(http_request)
        if result is None:
            body = "Path not found"
            headers = {"Content-Length": str(len(body))}
            result = HttpResponse(BAD_REQUEST, headers, body)

        return result