
if(NOT TARGET project2::project2)
    add_library(project2::project2 INTERFACE IMPORTED)
endif()

# Load the debug and release library finders
get_filename_component(_DIR "${CMAKE_CURRENT_LIST_FILE}" PATH)
file(GLOB CONFIG_FILES "${_DIR}/project2Target-*.cmake")

foreach(f ${CONFIG_FILES})
    include(${f})
endforeach()
