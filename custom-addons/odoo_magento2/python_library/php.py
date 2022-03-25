
try:  # Python3
    from urllib.parse import quote
except ImportError:  # Python2
    from urllib import quote

__version__ = "1.2.0"


class Php(object):

    @classmethod
    def http_build_query(cls, params, convention="%s"):
        """
        This was ripped shamelessly from a PHP forum and ported to Python:
          http://www.codingforums.com/showthread.php?t=72179

        Essentially, it's a (hopefully perfect) replica of PHP's
        http_build_query() that allows you to pass multi-dimensional arrays
        to a URL via POST or GET.
        Example:
          from php import Php
          Php.http_build_query({"x": [1,2,3]})
        """
        if len(params) == 0:
            return ""

        output = ""
        for key in params.keys():
            if type(params[key]) is dict:
                output = output + cls.http_build_query(params[key], convention % key + "[%s]")
            elif type(params[key]) is list:
                i = 0
                new_params = {}
                for element in params[key]:
                    new_params[str(i)] = element
                    i += 1
                output += cls.http_build_query(
                    new_params, convention % key + "[%s]")
            else:
                key = quote(key)
                val = quote(str(params[key]))
                output = output + convention % key + "=" + val + "&"
        return output
