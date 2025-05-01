import types

import vm
import vm_runner


def load_bytecode_from_file(filename: str) -> types.CodeType:
    with open(filename, 'r', encoding='utf-8') as f:
        source = f.read()

    code = vm_runner.compile_code(source)

    return code


def main():
    import sys

    if len(sys.argv) != 2:
        print("Использование: python main.py <файл_с_кодом>")
        sys.exit(1)

    filename = sys.argv[1]

    try:
        code_obj = vm_runner.compile_code(load_bytecode_from_file(filename))
        vm_out, vm_err, vm_exc = vm_runner.execute(code_obj, vm.VirtualMachine().run)
        print("=" * 15, "Result", "=" * 15)
        print(vm_out)
        print("=" * 15, "Errors", "=" * 15)
        print(vm_err)
        print("=" * 15, "Exceptions", "=" * 15)
        print(vm_exc)

    except FileNotFoundError:
        print(f"Ошибка: файл '{filename}' не найден")
    except Exception as e:
        print(f"Ошибка при выполнении: {str(e)}")


if __name__ == "__main__":
    main()
