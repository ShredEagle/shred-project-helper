cmake_minimum_required(VERSION 3.16)

# NOTE: Cannot set `VERSION ${BUILD_VERSION}` here, because the conanuser_config
# file defining the variable has not yet been included
project(Project3)

include(cmake/include.cmake)

cmc_include_conan_configuration()

include(cmc-install)
cmc_install_root_component_config(${PROJECT_NAME})
cmc_register_source_package(${PROJECT_NAME})

add_subdirectory(src)
