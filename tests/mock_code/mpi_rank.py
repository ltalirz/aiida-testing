#!/usr/bin/env python
from mpi4py import MPI

comm = MPI.COMM_WORLD
mpi_rank = comm.Get_rank()
print(mpi_rank)


def other_function():
    return comm.bcast(1, root=0)


if mpi_rank == 0:

    val = 1
    comm.Abort()
    # val = comm.bcast(val, root=0)
    #val = other_function()

else:
    val = comm.bcast(None, root=0)

print(val)

#     initialize()
# else:
#     req = comm.irecv(source=0, tag=1)
#     run_executable = req.wait()
#
#     if run_executable:
#         executable_path = os.environ[EnvKeys.EXECUTABLE_PATH.value]
#         subprocess.call([executable_path, *sys.argv[1:]])
