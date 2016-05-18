"""Setter functions for the Vasp calculator.

These are special keyword setters that are needed because a special
tag represents some set of keywords, e.g. the xc tag, or a change
implies multiple changes.

The general strategy is to construct a dictionary of the changes that
is passed back to the set function.

"""
import numpy as np
import vasp
from monkeypatch import monkeypatch_class
from ase.calculators.calculator import FileIOCalculator


@monkeypatch_class(vasp.Vasp)
def set(self, **kwargs):
    """Set parameters with keyword=value pairs.

    calc.set(xc='PBE')

    A few special kwargs are handled separately to expand them
    prior to setting the parameters. This is done to enable one
    set to track changes.

    """

    if 'xc' in kwargs:
        kwargs.update(self.set_xc_dict(kwargs['xc']))

    if 'ispin' in kwargs:
        kwargs.update(self.set_ispin_dict(kwargs['ispin']))

    if 'ldau_luj' in kwargs:
        kwargs.update(self.set_ldau_luj_dict(kwargs['ldau_luj']))

    if 'nsw' in kwargs:
        kwargs.update(self.set_nsw_dict(kwargs['nsw']))

    changed_parameters = FileIOCalculator.set(self, **kwargs)
    if changed_parameters:
        self.reset()
    return changed_parameters


@monkeypatch_class(vasp.Vasp)
def set_ispin_dict(self, val):
    """Returns dictionary of changes for ispin change."""
    # there are two ways to get magmom in.
    # 1. if you use magmom as a keyword, they are used.
    # 2. if you set magmom on each atom in an Atoms object and do not use
    # magmom then we use the atoms magmom, if we have ispin=2 set.
    # we set lorbit to 11 if ispin=2 so we can get the individual moments.
    if val is None:
        d = {}
        for key in ['ispin', 'magmom', 'lorbit']:
            if key in self.parameters:
                d[key] = None
        return d
    elif val == 1:
        d = {'ispin': 1}
        if 'magmom' in self.parameters:
            d['magmom'] = None
        if 'lorbit' in self.parameters:
            d['lorbit'] = None
        return d
    elif val == 2:
        d = {'ispin': 2}
        if 'magmom' not in self.parameters:
            d['magmom'] = [atom.magmom for atom
                            in self.atoms[self.resort]]
        # set individual magnetic moments.
        if 'lorbit' not in self.parameters:
            d['lorbit'] = 11

        return d


@monkeypatch_class(vasp.Vasp)
def set_rwigs_dict(self, val):
    """Return rwigs parameters."""
    d = {}
    if val is None:
        d['rwigs'] = None
        d['lorbit'] = None
    else:
        # val is a dictionary {sym: rwigs}
        # rwigs needs to be in the order of the potcars
        d['rwigs'] = [val[x[0]] for x in self.ppp_list]

    return d


@monkeypatch_class(vasp.Vasp)
def set_ldau_luj_dict(self, val):
    """Set the ldau_luj parameters."""
    if 'setups' in self.parameters:
        raise Exception('setups and ldau_luj is not supported.')

    if not hasattr(self, 'ppp_list'):
        atoms = self.get_atoms()
        self.sort_atoms(atoms)

    if val is not None:
        atom_types = [x[0] if isinstance(x[0], str)
                      else self.atoms[x[0]].symbol
                      for x in self.ppp_list]

        d = {}

        d['ldaul'] = [val[sym]['L'] for sym in atom_types]
        d['ldauu'] = [val[sym]['U'] for sym in atom_types]
        d['ldauj'] = [val[sym]['J'] for sym in atom_types]
        return d
    else:
        d = {}
        d['ldaul'] = None
        d['ldauu'] = None
        d['ldauj'] = None
        return d


@monkeypatch_class(vasp.Vasp)
def set_nbands(self, N=None, f=1.5):
    """Convenience function to set NBANDS to N or automatically compute
    nbands for non-spin-polarized calculations.

    nbands = int(nelectrons/2 + nions*f)

    this formula is suggested at
    http://cms.mpi.univie.ac.at/vasp/vasp/NBANDS_tag.html for
    transition metals f may be as high as 2.

    """
    if N is not None:
        self.set(nbands=int(N))
        return
    atoms = self.get_atoms()
    nelectrons = self.get_valence_electrons()
    nbands = int(np.ceil(nelectrons / 2.) + len(atoms) * f)
    self.set(nbands=nbands)


@monkeypatch_class(vasp.Vasp)
def set_nsw_dict(self, val):
    """Set nsw parameter.

    The default lwave behavior is False, but if nsw > 0 it makes sense
    to turn it on in case of restarts.

    """

    d = {'nsw': val}

    if val > 0:
        d['lwave'] = True
    elif val == 0:
        d['lwave'] = False
    else:
        d['lwave'] = False
    return d


@monkeypatch_class(vasp.Vasp)
def set_xc_dict(self, val):
    """Set xc parameter.

    Adds all the xc_defaults flags for the chosen xc.

    """
    d = {'xc': val}
    oxc = self.parameters.get('xc', None)
    if oxc:
        for key in vasp.Vasp.xc_defaults[oxc.lower()]:
            if key in self.parameters:
                d[key] = None
    d.update(vasp.Vasp.xc_defaults[val.lower()])
    return d
