"""Writer functions for vasp.py

Functions that write files: INCAR, POSCAR, POTCAR, KPOINTS

These are separated out by design to keep vasp.py small. Each function is
monkey-patched onto the Vasp class as if it were defined in vasp.py.

"""
import os
import numpy as np
from .vasp import Vasp, log
from vasp.monkeypatch import monkeypatch_class
from ase.calculators.calculator import FileIOCalculator


@monkeypatch_class(Vasp)
def write_input(self, atoms=None, properties=None, system_changes=None):
    """Writes all input files required for a calculation."""
    # this creates the directory if needed
    FileIOCalculator.write_input(self, atoms, properties, system_changes)

    if 'spring' not in self.parameters:  # do not write if NEB
        self.write_poscar()
    self.write_incar()
    if 'kspacing' not in self.parameters:
        self.write_kpoints()
    self.write_potcar()
    self.write_db()


@monkeypatch_class(Vasp)
def write_db(self,
             fname=None,
             atoms=None,
             parser=None,
             overwrite=True,
             keys={},
             data={},
             del_info=[],
             **kwargs):
    """Compile vasp calculation information into a database.
    primarily used to write the DB file. Only row 1 should be in
    the current DB database.

    :param fname: The name of the database to collect calculator
                  information in. Defaults to DB.db in vasp dir.
    :type fname: str

    :param atoms: An ASE atoms object to write to the database. If
                  None, the atoms object will be the image attached
                  to the calculator.
    :type atoms: object

    :param parser: A tool for generating key-value-pairs from the
                   calculators directory path. Pairs will be
                   separated by directory and key-values will be
                   separated by parser. If None, no key-value-pair
                   information will be collected.
    :type parser: str

    :param overwrite: Whether the database file should be overwritten
                      or not.
    :type overwrite: bool

    :param keys: Additional key-value-pairs to include in the database.
    :type keys: dict

    :param data: Additional data to include in the database.
    :type data: dict

    :param del_info: Keys to be removed from the data of key_value_pairs
                     of the DB file.
    :type del_info: list

    """
    from ase.db import connect

    if fname is None:
        fname = os.path.join(self.calc_dir, 'DB.db')

    # Get the atoms object from the calculator
    if atoms is None:
        atoms = self.get_atoms()

    # Get keys-value-pairs from directory name.
    # Collect only path names with 'parser' in them.
    if parser is not None:
        path = [x for x in self.calc_dir.split('/') if parser in x]

        for key_value in path:
            key = key_value.split(parser)[0]
            value = key_value.split(parser)[1]

            # Try to recognize characters and convert to
            # specific data types for easy access later.
            if '.' in value:
                value = float(value)
            elif value.isdigit():
                value = int(value)
            elif value == 'False':
                value = bool(False)
            elif value == 'True':
                value = bool(True)
            else:
                value = str(value)

            # Add directory keys
            keys[key] = value

    data.update({'path': self.calc_dir,
                 'version': self.version,
                 'resort': self.resort,
                 'parameters': self.parameters,
                 'ppp_list': self.ppp_list})
    log.debug('data = {}'.format(data))

    # Only relevant for writing single entry DB file.
    if overwrite:
        log.debug('overwriting db')
        if os.path.exists(fname):
            # Get any current data and keywords.
            with connect(fname) as db:
                try:
                    dbatoms = db.get_atoms(id=1)
                    data.update(dbatoms.data)
                    keys.update(dbatoms.key_value_pairs)
                except (AttributeError, KeyError):
                    pass
            os.unlink(fname)

        # Remove keys and data in del_info.
        for k in del_info:
            if k in keys:
                del keys[k]
            if k in data:
                del data[k]

    log.debug('writing db')

    # Generate the db file
    with connect(fname, use_lock_file=False) as db:
        log.debug('db handle: {}'.format(db))
        db.write(atoms, key_value_pairs=keys, data=data)

    log.debug('Done with db')

    return None


@monkeypatch_class(Vasp)
def write_poscar(self, fname=None):
    """Write the POSCAR file."""
    if fname is None:
        fname = os.path.join(self.calc_dir, 'POSCAR')

    from ase.io.vasp import write_vasp
    write_vasp(fname,
               self.atoms,
               symbol_count=self.symbol_count)


@monkeypatch_class(Vasp)
def write_incar(self, incar=None):
    """Writes out the INCAR file.

    Boolean values are written as .TRUE./.FALSE.
    integers/floats and strings are written out as is
    lists/tuples are written out as space separated values/

    """

    if incar is None:
        incar = os.path.join(self.calc_dir, 'INCAR')

    incar_keys = list(set(self.parameters) - set(self.special_kwargs))
    d = {key: self.parameters[key] for key in incar_keys}

    with open(incar, 'w') as f:
        f.write('INCAR created by Atomic Simulation Environment\n')
        for key, val in d.items():
            log.debug(f'"{key}", {val}, {type(val)}')
            key = ' ' + key.upper()
            if val is None:
                # Do not write out None values
                # It is how we delete tags
                continue
            # I am very unhappy about this special case. [2020-08-10 Mon] why is
            # there an extra space in front? You get the wrong result without
            # it.
            elif key == ' RWIGS':
                val = ' '.join(str(val[x[0]]) for x in self.ppp_list)
            elif isinstance(val, bool):
                val = '.TRUE.' if val else '.FALSE.'
            # Added [2020-08-10 Mon] for issue #57.
            elif isinstance(val, str):
                pass
            # elif isinstance(val, list) or isinstance(val, tuple):
            elif hasattr(val, '__iter__'):
                val = ' '.join(str(x) for x in val)
            f.write(f'{key} = {val}\n')


@monkeypatch_class(Vasp)
def write_kpoints(self, fname=None):
    """Write out the KPOINTS file.

    The KPOINTS file format is as follows:

    line 1: a comment
    line 2: number of kpoints
        n <= 0   Automatic kpoint generation
        n > 0    explicit number of kpoints
    line 3: kpt format
        if n > 0:
            C,c,K,k = cartesian coordinates
            anything else = reciprocal coordinates
        if n <= 0
            M,m,G,g for Monkhorst-Pack or Gamma grid
            anything else is a special case
    line 4: if n <= 0, the Monkhorst-Pack grid
        if n > 0, then a line per kpoint
    line 5: if n <=0 it is the gamma shift

    After the kpts may be tetrahedra, but we do now support that for
    now.

    """
    if fname is None:
        fname = os.path.join(self.calc_dir, 'KPOINTS')

    p = self.parameters

    kpts = p.get('kpts', None)  # this is a list, or None

    if kpts is None:
        NKPTS = None
    elif len(np.array(kpts).shape) == 1:
        NKPTS = 0  # automatic
    else:
        NKPTS = len(p['kpts'])

    # figure out the mode
    if NKPTS == 0:
        if p.get('gamma'):
            MODE = 'g'  # automatic gamma monkhorst-pack
        else:
            MODE = 'm'  # automatic monkhorst-pack
    # we did not trigger automatic kpoints
    elif p.get('kpts_nintersections', None) is not None:
        MODE = 'l'
    elif p.get('reciprocal', None) == True:
        MODE = 'r'
    else:
        MODE = 'c'

    with open(fname, 'w') as f:
        # line 1 - comment
        f.write('KPOINTS created by Atomic Simulation Environment\n')
        # line 2 - number of kpts
        if MODE in ['c', 'k', 'm', 'g', 'r']:
            f.write('{}\n'.format(NKPTS))
        elif MODE in ['l']:  # line mode, default intersections is 10
            f.write('{}\n'.format(p.get('kpts_nintersections')))

        # line 3
        if MODE in ['m', 'g']:
            if MODE == 'm':
                f.write('Monkhorst-Pack\n')
            elif MODE == 'g':
                f.write('Gamma\n')
        elif MODE in ['c', 'k']:
            f.write('Cartesian\n')
        elif MODE == 'l':
            f.write('Line-mode\n')
        else:
            f.write('Reciprocal\n')

        # kpoints lines
        points = list()
        if MODE in ['m', 'g']:
            points.append(p.get('kpts', (1, 1, 1)))
            if p.get('gamma'):
                points.append(p['gamma'])
            else:
                points.append(['0.0'] * 3)
        elif MODE in ['c', 'k', 'r']:
            points.append(p['kpts'])
            if any(len(point) != 4 for point in points):
                raise ValueError('Kpoint ERROR: weights must be provided')
        elif MODE == 'l':
            if p.get('reciprocal'):
                f.write('Reciprocal\n')
            else:
                f.write('Cartesian\n')
            points.append(p['kpts'])


        for point in points:
            text = ' '.join(map(str, point)) + '\n'
            f.write(text)


@monkeypatch_class(Vasp)
def write_potcar(self, fname=None):
    """Writes the POTCAR file.

    POTCARs are expected in $VASP_PP_PATH.

    """
    if fname is None:
        fname = os.path.join(self.calc_dir, 'POTCAR')

    with open(fname, 'wb') as potfile:
        for _, pfile, _ in self.ppp_list:
            pfile = os.path.join(os.environ['VASP_PP_PATH'], pfile)
            if not os.path.exists(pfile):
                raise Exception('{} does not exist', pfile)
            with open(pfile, 'rb') as f:
                potfile.write(f.read())
                log.debug('Added pfile')
