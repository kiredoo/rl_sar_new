cmake_minimum_required(VERSION 3.8)
project(motor_msg)

if($ENV{ROS_VERSION} STREQUAL 1)
  find_package(catkin REQUIRED COMPONENTS
    message_generation
  )

  add_message_files(
    FILES
    LowCmd.msg
    LowState.msg
    MotorCmd.msg
    MotorState.msg
  )

  generate_messages(
    DEPENDENCIES
  )

  catkin_package(
    CATKIN_DEPENDS
    message_runtime
  )

  install(
    DIRECTORY include/${PROJECT_NAME}/
    DESTINATION ${CATKIN_PACKAGE_INCLUDE_DESTINATION}
    FILES_MATCHING PATTERN "*.h"
  )

elseif($ENV{ROS_VERSION} STREQUAL 2)
  find_package(ament_cmake REQUIRED)
  find_package(rosidl_default_generators REQUIRED)

  rosidl_generate_interfaces(${PROJECT_NAME}
    "msg/LowCmd.msg"
    "msg/LowState.msg"
    "msg/MotorCmd.msg"
    "msg/MotorState.msg"
  )

  ament_export_dependencies(rosidl_default_runtime)
  ament_package()

endif()