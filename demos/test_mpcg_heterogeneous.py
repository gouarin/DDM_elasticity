from __future__ import print_function, division
import sys, petsc4py
petsc4py.init(sys.argv)
import mpi4py.MPI as mpi
from petsc4py import PETSc
import numpy as np
from elasticity import *

def rhs(coords, rhs):
    n = rhs.shape
    #rand = np.random.random(n[:-1])
    rhs[..., 1] = -9.81# + rand

OptDB = PETSc.Options()
Lx = OptDB.getInt('Lx', 10)
Ly = OptDB.getInt('Ly', 1)
n  = OptDB.getInt('n', 16)
nx = OptDB.getInt('nx', Lx*n)
ny = OptDB.getInt('ny', Ly*n)

hx = Lx/(nx - 1)
hy = Ly/(ny - 1)

da = PETSc.DMDA().create([nx, ny], dof=2, stencil_width=1)
da.setUniformCoordinates(xmax=Lx, ymax=Ly)

## constant young modulus
#E = 30000
## constant Poisson coefficient
#nu = 0.4

def lame_coeff(x, y, v1, v2):
    output = np.empty(x.shape)
    mask = np.logical_or(np.logical_and(.2<=y, y<=.4),np.logical_and(.6<=y, y<=.8))
    output[mask] = v1
    output[np.logical_not(mask)] = v2
    return output

# non constant young modulus
E = buildCellArrayWithFunction(da, lame_coeff, (10**6,1))
# non constant Poisson coefficient
nu = buildCellArrayWithFunction(da, lame_coeff, (0.4, 0.4))

lamb = (nu*E)/((1+nu)*(1-2*nu)) 
mu = .5*E/(1+nu)

x = da.createGlobalVec()
b = buildRHS(da, [hx, hy], rhs)
A = buildElasticityMatrix(da, [hx, hy], lamb, mu)
A.assemble()

bcApplyWest(da, A, b)

RBM = PETSc.NullSpace().createRigidBody(da.getCoordinates())
rbm_vecs = RBM.getVecs()
for rbm_vec in rbm_vecs:
    bcApplyWest_vec(da, rbm_vec)

proj = projection(da, A, RBM)

asm = MP_ASM(da, proj, [hx, hy], lamb, mu)
P = PETSc.Mat().createPython(
    [x.getSizes(), b.getSizes()], comm=da.comm)
P.setPythonContext(asm)
P.setUp()

# Set initial guess
xtild = proj.xcoarse(b)
bcopy = b.copy()
b -= A*xtild

x.setRandom()
bcApplyWest_vec(da, x)
proj.apply(x)
xnorm = b.dot(x)/x.dot(A*x)
x *= xnorm

ksp = PETSc.KSP().create()
ksp.setOperators(A)
ksp.setType(ksp.Type.PYTHON)
ksp.setPythonContext(KSP_MPCG(asm))
ksp.setInitialGuessNonzero(True)

ksp.solve(b, x)

norm = (A*x-b).norm()
if mpi.COMM_WORLD.rank == 0:
    print(f'norm of the projected residual {norm}')

x += xtild
viewer = PETSc.Viewer().createVTK('solution_2d_asm.vts', 'w', comm = PETSc.COMM_WORLD)
x.view(viewer)

norm = (A*x-bcopy).norm()
if mpi.COMM_WORLD.rank == 0:
    print(f'norm of the complete residual {norm}')