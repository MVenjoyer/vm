"""
Simplified VM code which works for some cases.
You need extend/rewrite code to pass all cases.
"""

import builtins
import dis
import operator
import types
import typing as tp

CO_VARARGS = 4
CO_VARKEYWORDS = 8

ERR_TOO_MANY_POS_ARGS = 'Too many positional arguments'
ERR_TOO_MANY_KW_ARGS = 'Too many keyword arguments'
ERR_MULT_VALUES_FOR_ARG = 'Multiple values for arguments'
ERR_MISSING_POS_ARGS = 'Missing positional arguments'
ERR_MISSING_KWONLY_ARGS = 'Missing keyword-only arguments'
ERR_POSONLY_PASSED_AS_KW = 'Positional-only argument passed as keyword argument'


def bind_args(code: types.CodeType, default: list[tp.Any], kw_default: dict[tp.Any, tp.Any], *args: tp.Any,
              **kwargs: tp.Any) -> dict[str, tp.Any]:
    flags = code.co_flags
    varargs = flags & CO_VARARGS == CO_VARARGS
    varkeywords = flags & CO_VARKEYWORDS == CO_VARKEYWORDS
    variables = code.co_varnames
    args_amount = code.co_argcount
    pos_only_amount = code.co_posonlyargcount
    name_only_amount = code.co_kwonlyargcount
    default_len = len(default)
    answer: dict[str, tp.Any] = {}
    pos = 0
    name = 0
    used_kwargs = set()
    used_pos_args = set()
    for i in range(pos_only_amount):
        if i < len(args):
            used_pos_args.add(variables[i])
            answer[variables[i]] = args[i]
            pos += 1
        elif variables[i] in kwargs:
            if pos_only_amount > len(args) and varkeywords:
                raise TypeError(ERR_MISSING_POS_ARGS)
            raise TypeError(ERR_POSONLY_PASSED_AS_KW)
        elif (x := i - (args_amount - default_len)) < 0:
            raise TypeError(ERR_MISSING_POS_ARGS)
        else:
            used_pos_args.add(variables[i])
            answer[variables[i]] = default[x]
            pos += 1
    for i in range(pos_only_amount, args_amount):
        if pos < len(args):
            answer[variables[i]] = args[i]
            pos += 1
        elif name < len(args) + len(kwargs) and variables[i] in kwargs:
            answer[variables[i]] = kwargs[variables[i]]
            used_kwargs.add(variables[i])
            name += 1
        elif (x := i - (args_amount - default_len)) < 0:
            for el in kwargs.keys():
                if el in answer and el not in used_kwargs:
                    raise TypeError(ERR_POSONLY_PASSED_AS_KW)
            raise TypeError(ERR_MISSING_POS_ARGS)
        elif default:
            for el in kwargs.keys():
                if el in answer and el not in used_kwargs:
                    raise TypeError(ERR_POSONLY_PASSED_AS_KW)
            answer[variables[i]] = default[x]
            pos += 1
    if pos < len(args) and not varargs:
        raise TypeError(ERR_TOO_MANY_POS_ARGS)
    for i in range(args_amount, args_amount + name_only_amount):
        if variables[i] in kwargs:
            answer[variables[i]] = kwargs[variables[i]]
            used_kwargs.add(variables[i])
            name += 1
        elif kw_default and variables[i] in kw_default:
            answer[variables[i]] = kw_default[variables[i]]
            used_kwargs.add(variables[i])
            name += 1
        else:
            raise TypeError(ERR_MISSING_KWONLY_ARGS)
    if name < len(kwargs):
        for key in answer:
            if key not in used_pos_args:
                if key in kwargs and key not in used_kwargs and key in answer:
                    raise TypeError(ERR_MULT_VALUES_FOR_ARG)
                elif not varkeywords:
                    raise TypeError(ERR_MISSING_POS_ARGS)
        if not varkeywords:
            raise TypeError(ERR_TOO_MANY_KW_ARGS)
    if varargs:
        answer[variables[args_amount + name_only_amount]] = args[pos:]
    if varkeywords:
        answer[variables[args_amount + name_only_amount + (1 if varargs else 0)]] = {k: v for k, v in kwargs.items()
                                                                                     if
                                                                                     k not in used_kwargs}
    return answer


class Frame:
    """
    Frame header in cpython with description
        https://github.com/python/cpython/blob/3.12/Include/internal/pycore_frame.h

    Text description of frame parameters
        https://docs.python.org/3/library/inspect.html?highlight=frame#types-and-members
    """

    def __init__(self,
                 frame_code: types.CodeType,
                 frame_builtins: dict[str, tp.Any],
                 frame_globals: dict[str, tp.Any],
                 frame_locals: dict[str, tp.Any]) -> None:
        self.code = frame_code
        self.builtins = frame_builtins
        self.globals = frame_globals
        self.locals = frame_locals
        self.data_stack: tp.Any = []
        self.return_value = None
        self.instructions_pointer = 0
        self.offset = -1
        self.current_instruction: tp.Any = None
        self.last_instruction: tp.Any = None
        self.depth = 0

    def top(self) -> tp.Any:
        return self.data_stack[-1]

    def pop(self) -> tp.Any:
        return self.data_stack.pop()

    def push(self, *values: tp.Any) -> None:
        self.data_stack.extend(values)

    def popn(self, n: int) -> tp.Any:
        """
        Pop a number of values from the value stack.
        A list of n values is returned, the deepest value first.
        """
        if n > 0:
            returned = self.data_stack[-n:]
            self.data_stack[-n:] = []
            return returned
        else:
            return []

    def run(self) -> tp.Any:
        instructions = list(dis.get_instructions(self.code))
        jumping_dct = {value.offset: i for i, value in enumerate(instructions)}
        while self.instructions_pointer < len(instructions) and self.depth > -1:
            self.last_instruction = self.current_instruction
            self.current_instruction = instructions[self.instructions_pointer]
            getattr(self, self.current_instruction.opname.lower() + "_op")(self.current_instruction.argval)
            if self.offset != -1:
                self.instructions_pointer = jumping_dct.get(self.offset, self.instructions_pointer + 1)
                self.offset = -1
            else:
                self.instructions_pointer += 1
        return self.return_value

    def resume_op(self, arg: int) -> tp.Any:
        pass

    def push_null_op(self, _: tp.Any) -> tp.Any:
        self.push(None)

    def precall_op(self, arg: int) -> tp.Any:
        pass

    def call_op(self, arg: int) -> None:
        args: list[tp.Any] = []
        kw = 0
        ag = 0
        for i in range(arg):
            if callable(self.top()):
                break
            args.append(self.pop())
        args = args[::-1]
        if len(args) != arg:
            kw = 0 if not args or not isinstance(args[-1], dict) else len(args[-1])
        if len(args) + kw < arg:
            if kw:
                ag = 0 if len(args) <= 1 or not isinstance(args[-2], tuple) else len(args[-2])
            else:
                ag = 0 if not args or not isinstance(args[-1], tuple) else len(args[-1])
        a: list[tp.Any] = []
        while len(args) + len(a) + kw + ag < arg:
            a.append(self.pop())
        args = a[::-1] + args
        callable_object = self.pop()
        if self.data_stack and self.top() is None:
            self.pop()
        if self.last_instruction.opname == 'KW_NAMES':
            positional_args = []
            kwargs = {}
            for el in args:
                if isinstance(el, dict):
                    kwargs.update(el)
                else:
                    positional_args.append(el)
            self.push(callable_object(*positional_args, **kwargs))
        else:
            self.push(callable_object(*args))
        if callable_object not in self.builtins.values():
            self.depth += 1

    def call_function_ex_op(self, flags: int) -> None:
        kwargs = {}
        if flags % 2 == 1:
            kwargs = self.pop()
        arg = self.pop()
        callable_obj = self.pop()
        self.push(callable_obj(*arg, **kwargs))
        self.depth += 1

    def dict_merge_op(self, _: tp.Any) -> None:
        dct = self.pop()
        self.data_stack[-1].update(dct)

    def dict_update_op(self, i: int) -> None:
        dct = self.pop()
        dict.update(self.data_stack[-i], dct)

    def kw_names_op(self, consti: tuple[str]) -> None:
        kw_names = {}
        for key, value in zip(consti, self.popn(len(consti))):
            kw_names[key] = value
        self.push(kw_names)

    def load_name_op(self, arg: str) -> None:
        if arg in self.locals:
            self.push(self.locals[arg])
        elif arg in self.globals:
            self.push(self.globals[arg])
        elif arg in self.builtins:
            self.push(self.builtins[arg])
        else:
            raise NameError(f"name '{arg}' is not defined")

    def load_global_op(self, arg: str) -> None:
        if arg in self.globals:
            self.push(self.globals[arg])
        elif arg in self.builtins:
            self.push(self.builtins[arg])
        else:
            raise NameError(f"name '{arg}' is not defined")

    def load_const_op(self, arg: tp.Any) -> None:
        self.push(arg)

    def return_value_op(self, _: tp.Any) -> None:
        self.return_value = self.pop()
        self.depth -= 1

    def return_const_op(self, arg: tp.Any) -> None:
        self.return_value = arg
        self.depth -= 1

    def pop_top_op(self, _: tp.Any) -> None:
        self.pop()

    def nop_op(self, _: tp.Any) -> None:
        pass

    def make_function_op(self, arg: int) -> None:
        code = self.pop()

        defaults = []
        kw_defaults = {}

        if arg & 0x01:
            defaults = self.pop()

        if arg & 0x02:
            kw_defaults = self.pop()

        def f(*args: tp.Any, **kwargs: tp.Any) -> tp.Any:
            answer = bind_args(code, defaults, kw_defaults, *args, **kwargs)
            f_locals = dict(self.locals)
            f_locals.update(answer)
            frame = Frame(code, self.builtins, self.globals, f_locals)
            return frame.run()

        self.push(f)

    def store_name_op(self, arg: str) -> None:
        const = self.pop()
        self.locals[arg] = const

    def store_global_op(self, arg: str) -> None:
        const = self.pop()
        self.globals[arg] = const

    def store_subscr_op(self, _: tp.Any) -> None:
        key = self.pop()
        container = self.pop()
        value = self.pop()
        container[key] = value

    def load_attr_op(self, namei: str) -> None:
        self.push(getattr(self.pop(), namei))

    def store_attr_op(self, namei: str) -> None:
        obj = self.pop()
        value = self.pop()
        setattr(obj, namei, value)

    def delete_attr_op(self, namei: str) -> None:
        delattr(self.pop(), namei)

    def format_value_op(self, flags: tuple[tp.Any]) -> None:
        if flags[0] is None:
            return
        else:
            self.push(flags[0](self.pop()))

    def build_string_op(self, arg: int) -> None:
        self.push("".join(self.popn(arg)))

    def binary_op_op(self, op: int) -> None:
        binary_operations = {
            0: operator.add,
            1: operator.and_,
            2: operator.floordiv,
            3: operator.lshift,
            4: operator.matmul,
            5: operator.mul,
            6: operator.mod,
            7: operator.or_,
            8: operator.pow,
            9: operator.rshift,
            10: operator.sub,
            11: operator.truediv,
            12: operator.xor,
            13: operator.iadd,
            14: operator.iand,
            15: operator.ifloordiv,
            16: operator.ilshift,
            17: operator.imatmul,
            18: operator.imul,
            19: operator.imod,
            20: operator.ior,
            21: operator.ipow,
            22: operator.irshift,
            23: operator.isub,
            24: operator.itruediv,
            25: operator.ixor,
        }

        rhs = self.pop()
        lhs = self.pop()
        if op in binary_operations:
            result = binary_operations[op](lhs, rhs)
            self.push(result)
        else:
            raise ValueError(f"Unsupported binary operation '{op}'")

    def compare_op_op(self, op: str) -> None:
        compare_operations = {
            '==': operator.eq,
            '!=': operator.ne,
            '<': operator.lt,
            '<=': operator.le,
            '>': operator.gt,
            '>=': operator.ge
        }

        rhs = self.pop()
        lhs = self.pop()

        if op in compare_operations:
            result = compare_operations[op](lhs, rhs)
            self.push(result)
        else:
            raise ValueError(f"Unsupported compare operation '{op}'")

    def pop_except_op(self, _: tp.Any) -> None:
        if self.data_stack:
            self.pop()

    def copy_op(self, i: int) -> None:
        if self.data_stack:
            self.push(self.data_stack[-i])

    def swap_op(self, i: int) -> None:
        self.data_stack[-i], self.data_stack[-1] = self.data_stack[-1], self.data_stack[-i]

    def is_op_op(self, invert: int) -> None:
        if invert == 1:
            self.push(self.pop() is not self.pop())
        else:
            self.push(self.pop() is self.pop())

    def unary_negative_op(self, _: tp.Any) -> None:
        self.data_stack[-1] = -self.data_stack[-1]

    def call_intrinsic_1_op(self, _: tp.Any) -> None:
        match self.current_instruction.argrepr:
            case 'INTRINSIC_UNARY_POSITIVE':
                self.push(+self.pop())
            case 'INTRINSIC_IMPORT_STAR':
                module_dict = vars(self.pop())
                for name, value in module_dict.items():
                    if not name.startswith("_"):
                        self.globals[name] = value
                self.push(None)
            case 'INTRINSIC_LIST_TO_TUPLE':
                self.push(tuple(self.pop()))
            case 'INTRINSIC_PRINT':
                print(self.pop())

    def unary_not_op(self, _: tp.Any) -> None:
        self.data_stack[-1] = not self.data_stack[-1]

    def unary_invert_op(self, _: tp.Any) -> None:
        self.data_stack[-1] = ~self.data_stack[-1]

    def contains_op_op(self, invert: int) -> None:
        x = self.pop()
        if invert == 1:
            self.push(self.pop() not in x)
        else:
            self.push(self.pop() in x)

    def binary_slice_op(self, _: tp.Any) -> None:
        end = self.pop()
        start = self.pop()
        container = self.pop()
        self.push(container[start:end])

    def build_slice_op(self, arg: int) -> None:
        if arg == 3:
            step = self.pop()
            end = self.pop()
            start = self.pop()
            self.push(slice(start, end, step))
        else:
            end = self.pop()
            start = self.pop()
            self.push(slice(start, end))

    def binary_subscr_op(self, _: tp.Any) -> None:
        key = self.pop()
        container = self.pop()
        self.push(container[key])

    def build_list_op(self, arg: int) -> None:
        if arg == 0:
            value = []
        else:
            value = list(self.data_stack[-arg:])
            self.data_stack = self.data_stack[:-arg]
        self.push(value)

    def list_extend_op(self, arg: int) -> None:
        seq = self.pop()
        list.extend(self.data_stack[-arg], seq)

    def list_append_op(self, arg: int) -> None:
        seq = self.pop()
        list.append(self.data_stack[-arg], seq)

    def store_fast_op(self, var_num: str) -> None:
        self.locals[var_num] = self.pop()

    def load_fast_op(self, var_num: str) -> None:
        if var_num in self.locals:
            self.push(self.locals[var_num])

    def delete_fast_op(self, var_num: str) -> None:
        if var_num in self.locals:
            del self.locals[var_num]

    def delete_global_op(self, var_num: str) -> None:
        if var_num in self.globals:
            del self.globals[var_num]

    def load_fast_check_op(self, var_num: str) -> None:
        if var_num in self.locals:
            self.push(self.locals[var_num])
        else:
            raise UnboundLocalError(f"Local variable '{var_num}' is not defined")

    def load_fast_and_clear_op(self, var_num: str) -> None:
        if var_num in self.locals:
            self.push(self.locals[var_num])
            del self.locals[var_num]
        else:
            self.push(None)

    def import_name_op(self, arg: str) -> None:
        first, second = self.popn(2)
        module = __import__(arg, globals=self.globals, locals=self.locals, fromlist=second, level=first)
        self.push(module)

    def import_from_op(self, arg: str) -> None:
        module = self.top()
        self.push(getattr(module, arg))

    def build_map_op(self, arg: int) -> None:
        new_dict = {}
        for _ in range(arg):
            value = self.pop()
            key = self.pop()
            new_dict[key] = value
        self.push(new_dict)

    def map_add_op(self, i: int) -> None:
        value = self.pop()
        key = self.pop()
        dict.__setitem__(self.data_stack[-i], key, value)

    def build_const_key_map_op(self, arg: int) -> None:
        keys = self.pop()
        values = self.popn(arg)
        self.push({key: value for key, value in zip(keys, values)})

    def build_tuple_op(self, arg: int) -> None:
        if arg == 0:
            value = ()
        else:
            value = tuple(self.data_stack[-arg:])
            self.data_stack = self.data_stack[:-arg]

        self.push(value)

    def build_set_op(self, arg: int) -> None:
        if arg == 0:
            value = set()
        else:
            value = set(self.data_stack[-arg:])
            self.data_stack = self.data_stack[:-arg]

        self.push(value)

    def set_add_op(self, i: int) -> None:
        item = self.pop()
        set.add(self.data_stack[-i], item)

    def set_update_op(self, arg: int) -> None:
        seq = self.pop()
        set.update(self.data_stack[-arg], seq)

    def store_slice_op(self, _: tp.Any) -> None:
        end = self.pop()
        start = self.pop()
        container = self.pop()
        values = self.pop()
        container[start:end] = values
        self.push(container)

    def delete_subscr_op(self, _: tp.Any) -> None:
        key = self.pop()
        container = self.pop()
        del container[key]

    def delete_name_op(self, arg: str) -> None:
        if arg in self.builtins:
            del self.builtins[arg]
        if arg in self.locals:
            del self.locals[arg]
        if arg in self.globals:
            del self.globals[arg]

    def unpack_sequence_op(self, count: int) -> None:
        assert (len(self.top()) == count)
        self.data_stack.extend(self.pop()[:-count - 1:-1])

    def pop_jump_if_false_op(self, delta: int) -> None:
        if not self.pop():
            self.offset = delta

    def pop_jump_if_true_op(self, delta: int) -> None:
        if self.pop():
            self.offset = delta

    def pop_jump_if_none_op(self, delta: int) -> None:
        if self.pop() is None:
            self.offset = delta

    def jump_backward_op(self, delta: int) -> None:
        self.offset = delta

    def jump_forward_op(self, delta: int) -> None:
        self.offset = delta

    def load_assertion_error_op(self, _: tp.Any) -> None:
        self.push(AssertionError)

    def raise_varargs_op(self, argc: int) -> None:
        match argc:
            case 0:
                raise
            case 1:
                raise self.pop()
            case 2:
                exc, cause = self.popn(2)
                raise exc from cause
            case _:
                raise ValueError(f"Unsupported raise_varargs_op argc '{argc}'")

    def get_iter_op(self, _: tp.Any) -> None:
        self.push(iter(self.pop()))

    def for_iter_op(self, delta: int) -> None:
        try:
            iterator = self.top()
            next_value = next(iterator)
            self.push(next_value)
        except StopIteration:
            self.offset = delta

    def end_for_op(self, _: tp.Any) -> None:
        self.pop()


class VirtualMachine:
    def run(self, code_obj: types.CodeType) -> None:
        """
        :param code_obj: code for interpreting
        """
        globals_context: dict[str, tp.Any] = {}
        frame = Frame(code_obj, builtins.globals()['__builtins__'], globals_context, globals_context)
        return frame.run()
