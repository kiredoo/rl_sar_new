import subprocess


def get_func_argument_by_mangled_name(mangled_name):
    try:
        proc_output = subprocess.check_output(["c++filt", mangled_name], encoding="utf-8")
    except subprocess.CalledProcessError:
        return ""

    if "(" in proc_output:
        args = proc_output.split("(", maxsplit=1)[1].strip()
        return args[:-1] # the last char ) should be removed
    else:
        return ""

def demangle(mangled_name):
    try:
        proc_output = subprocess.check_output(["c++filt", mangled_name], encoding="utf-8")
        return proc_output.split("(", maxsplit=1)[0].strip()
    except subprocess.CalledProcessError:
        return ""

def does_arg_contain_msg(mangled_name):
    return bool("::msg::" in get_func_argument_by_mangled_name(mangled_name))
