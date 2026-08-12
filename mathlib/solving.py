import sympy as sp


def my_solve(*args, **kwargs):
    result = sp.solve(*args, **kwargs)

    if isinstance(result, list):
        filtered = []

        for sol in result:
            if isinstance(sol, dict):
                is_real = all(getattr(v, "is_real", None) is True for v in sol.values())
            elif isinstance(sol, (list, tuple)):
                is_real = all(getattr(v, "is_real", None) is True for v in sol)
            else:
                is_real = getattr(sol, "is_real", None) is True

            if is_real:
                filtered.append(sol)

        result = filtered

        if len(result) == 1 and not isinstance(result[0], dict):
            return result[0]

    return result


def my_csolve(*args, **kwargs):
    result = sp.solve(*args, **kwargs)

    if isinstance(result, list) and len(result) == 1 and not isinstance(result[0], dict):
        return result[0]

    return result
