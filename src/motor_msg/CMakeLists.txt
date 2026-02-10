cmake_minimum_required(VERSION 2.8.3)
project(motor_msg)

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

#############
## Install ##
#############

# Mark topic names header files for installation
install(
  DIRECTORY include/${PROJECT_NAME}/
  DESTINATION ${CATKIN_PACKAGE_INCLUDE_DESTINATION}
  FILES_MATCHING PATTERN "*.h"
)