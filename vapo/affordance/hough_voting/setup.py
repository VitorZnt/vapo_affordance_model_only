from setuptools import setup
from torch.utils.cpp_extension import BuildExtension, CUDAExtension

# If you do not have sudo priviledges
# Change to include_dirs = '/path_to_eigen/eigen-git-mirror/'

setup(
    name="hough_voting",
    ext_modules=[
        CUDAExtension(
            name="hough_voting_cuda",
            sources=["hough_voting_layer.cpp", "hough_voting_kernel.cu"],
            include_dirs=["/usr/local/include/eigen3", "/usr/include"],
        )
    ],
    cmdclass={"build_ext": BuildExtension},
)
