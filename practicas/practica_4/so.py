#!/usr/bin/env python

from hardware import *
import log

## emulates a compiled program
from practicas.practica_4.tabulate import tabulate


class Program:

    def __init__(self, name, instructions):
        self._name = name
        self._instructions = self.expand(instructions)


    @property
    def name(self):
        return self._name

    @property
    def instructions(self):
        return self._instructions

    def addInstr(self, instruction):
        self._instructions.append(instruction)

    def expand(self, instructions):
        expanded = []
        for i in instructions:
            if isinstance(i, list):
                ## is a list of instructions
                expanded.extend(i)
            else:
                ## a single instr (a String)
                expanded.append(i)

        ## now test if last instruction is EXIT
        ## if not... add an EXIT as final instruction
        last = expanded[-1]
        if not ASM.isEXIT(last):
            expanded.append(INSTRUCTION_EXIT)

        return expanded

    def __repr__(self):
        return "Program({name}, {instructions})".format(name=self._name, instructions=self._instructions)


## emulates an Input/Output device controller (driver)
class IoDeviceController():

    def __init__(self, device):
        self._device = device
        self._waiting_queue = []
        self._currentPCB = None

    def runOperation(self, pcb, instruction):
        pair = {'pcb': pcb, 'instruction': instruction}
        # append: adds the element at the end of the queue
        self._waiting_queue.append(pair)
        # try to send the instruction to hardware's device (if is idle)
        self.__load_from_waiting_queue_if_apply()

    def getFinishedPCB(self):
        finishedPCB = self._currentPCB
        self._currentPCB = None
        self.__load_from_waiting_queue_if_apply()
        return finishedPCB

    def __load_from_waiting_queue_if_apply(self):
        if (len(self._waiting_queue) > 0) and self._device.is_idle:
            ## pop(): extracts (deletes and return) the first element in queue
            pair = self._waiting_queue.pop(0)
            #print(pair)
            pcb = pair['pcb']
            instruction = pair['instruction']
            self._currentPCB = pcb
            self._device.execute(instruction)

    def __repr__(self):
        return "IoDeviceController for {deviceID} running: {currentPCB} waiting: {waiting_queue}".format(deviceID=self._device.deviceId, currentPCB=self._currentPCB, waiting_queue=self._waiting_queue)


## ############################## SCHEDULERS ########################################
## ############################## ABSTRACT SCHEDULER ########################################

class AbstractScheduler:

    def __init__(self):
        self._readyQueue = ReadyQueue()

    @property
    def readyQueue(self):
        return self._readyQueue

################################ FCFS SCHEDULER ########################################


class FCFSScheduler(AbstractScheduler):
        
    def getPcb(self):
        return self.readyQueue.getNextPcb()

    def mustExpropiate(self, pcb, pcbInCpu):
        return False

################################ ROUND ROBIN SCHEDULER ########################################


class RoundRobinScheduler(AbstractScheduler):

    def __init__(self, quantum):
        self._readyQueue = ReadyQueue()
        HARDWARE.timer.quantum = quantum

    def getPcb(self):
        return self.readyQueue.getNextPcb()

    def mustExpropiate(self, pcb, pcbInCpu):
        return False

################################ PRIORITY SCHEDULER ########################################


class PriorityScheduler(AbstractScheduler):

    def getPcb(self):
        return self.readyQueue.getNextPcbMayorPrioridad()

################################ PRIORITY NO EXPROPIATIVO SCHEDULER ########################################


class PriorityNoExpropiativoScheduler(PriorityScheduler):

    def mustExpropiate(self, pcb, pcbInCpu):
        return False

############################### PRIORITY EXPROPIATIVO SCHEDULER ########################################

class PriorityExpropiativoScheduler(PriorityScheduler):

    def mustExpropiate(self, pcb, pcbInCpu):
        return pcb.priority < pcbInCpu.priority


## emulates the  Interruptions Handlers
class AbstractInterruptionHandler():

    def __init__(self, kernel):
        self._kernel = kernel

    @property
    def kernel(self):
        return self._kernel

    def execute(self, irq):
        log.logger.error("-- EXECUTE MUST BE OVERRIDEN in class {classname}".format(classname=self.__class__.__name__))

    def handlerIn(self, pcb):
        if self.kernel.pcbTable.runningPCB is None:
            self.kernel.dispatcher.load(pcb)
            pcb.state = "running"
            self.kernel.pcbTable.runningPCB = pcb
        else:
            pcbInCpu = self.kernel.pcbTable.runningPCB
            if self.kernel.scheduler.mustExpropiate(pcb, pcbInCpu):
                pcbExpropiado = pcbInCpu
                pcbExpropiado.state = "ready"
                self.kernel.dispatcher.save(pcbExpropiado)
                self.kernel.scheduler.readyQueue.add(pcbExpropiado)
                self.kernel.dispatcher.load(pcb)
                pcb.state = "running"
                self.kernel.pcbTable.runningPCB = pcb
            else:
                pcb.state = "ready"
                self.kernel.scheduler.readyQueue.add(pcb)

    def handlerOut(self):
        if self.kernel.scheduler.readyQueue.lista:
            nextPCB = self.kernel.scheduler.getPcb()
            nextPCB.state = "running"
            self.kernel.dispatcher.load(nextPCB)
            self.kernel.pcbTable.runningPCB = nextPCB


class KillInterruptionHandler(AbstractInterruptionHandler):

    def execute(self, irq):
        log.logger.info(" Program Finished ")
        pcb = self.kernel.pcbTable.runningPCB
        self.kernel.dispatcher.save(pcb)
        pcb.state = "terminated"
        self.kernel.pcbTable.remove(pcb.pid)
        self.kernel.pcbTable.runningPCB = None
        self.handlerOut()


class IoInInterruptionHandler(AbstractInterruptionHandler):

    def execute(self, irq):
        program = irq.parameters
        pcb = self.kernel.pcbTable.runningPCB
        self.kernel.pcbTable.runningPCB = None
        self.kernel.dispatcher.save(pcb)
        pcb.state = "waiting"
        self.kernel.ioDeviceController.runOperation(pcb, program)
        log.logger.info(self.kernel.ioDeviceController)
        self.handlerOut()


class IoOutInterruptionHandler(AbstractInterruptionHandler):

    def execute(self, irq):
        pcb = self.kernel.ioDeviceController.getFinishedPCB()
        log.logger.info(self.kernel.ioDeviceController)
        self.handlerIn(pcb)


class NewInterruptionHandler(AbstractInterruptionHandler):

    def execute(self, irq):
        program = irq.parameters[0]
        priority = irq.parameters[1]
        baseDir = self.kernel.loader.load(program)
        pid = self.kernel.pcbTable.getNewPID()
        pcb = PCB(baseDir, pid, 0, program.name, priority)
        self.kernel.pcbTable.add(pcb)
        self.handlerIn(pcb)


class TimeoutInterruptionHandle(AbstractInterruptionHandler):

    def execute(self, irq):
        if self.kernel.scheduler.readyQueue.lista:
            pcbCorriendo = self.kernel.pcbTable.runningPCB
            pcbCorriendo.state = "ready"
            self.kernel.dispatcher.save(pcbCorriendo)
            self.kernel.scheduler.readyQueue.add(pcbCorriendo)
            self.kernel.pcbTable.runningPCB = None
            self.handlerOut()
        else:
            HARDWARE.timer.reset()

################################ LOADER ########################################


class Loader:

    def __init__(self):
        self._baseDir = 0
        self._proximaBaseDir = 0

    @property
    def baseDir(self):
        return self._baseDir

    @baseDir.setter
    def baseDir(self, baseDir):
        self._baseDir = baseDir

    @property
    def proximaBaseDir(self):
        return self._proximaBaseDir

    @proximaBaseDir.setter
    def proximaBaseDir(self, proximaBaseDir):
        self._proximaBaseDir = proximaBaseDir

    def load(self, program):
        # loads the program in main memory
        progSize = len(program.instructions)
        self.celdaContador = self.proximaBaseDir
        self.baseDir = self.proximaBaseDir
        for index in range(0, progSize):
            inst = program.instructions[index]
            HARDWARE.memory.write(self.celdaContador, inst)
            self.celdaContador = self.celdaContador + 1
        self.proximaBaseDir = self.celdaContador
        return self.baseDir

################################ READY QUEUE ########################################

class ReadyQueue:

    def __init__(self):
        self._lista = []

    def add(self, pcb):
        self._lista.append(pcb)

    def remove(self, pcb):
        self._lista.remove(pcb)

    @property
    def lista(self):
        return self._lista

    def getNextPcb(self):
        pcb = self._lista[0]
        self.remove(pcb)
        return pcb

    def getNextPcbMayorPrioridad(self):
        contador = 0
        for pcb in self.lista:
            if pcb.priority > contador:
                pcbBuscado = pcb
        self.remove(pcbBuscado)
        return pcbBuscado

################################ PCB ########################################


class PCB:

    def __init__(self, baseDir, pid, pc, nombre, priority):
        self._baseDir = baseDir
        self._pid = pid
        self._pc = pc
        self._state = "new"
        self._path = nombre
        self._priority = priority

    @property
    def baseDir(self):
        return self._baseDir

    @property
    def priority(self):
        return self._priority

    @property
    def pid(self):
        return self._pid

    @property
    def pc(self):
        return self._pc

    @pc.setter
    def pc(self, pc):
        self._pc = pc

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, state):
        self._state = state

    @property
    def path(self):
        return self._path

    def __repr__(self):
        return "PCB(pid={}, baseDir={}, pc={}, state={}, path={}, priority={})".format(self.pid, self.baseDir, self.pc, self.state, self.path, self.priority)

################################ PCBTABLE ########################################


class PCBTable:

    def __init__(self):
        self._tabla = []
        self._pid = -1
        self._runningPcb = None

    @property
    def tabla(self):
        return self._tabla

    @property
    def pid(self):
        return self._pid

    @pid.setter
    def pid(self, pid):
        self._pid = pid

    @property
    def runningPCB(self):
        return self._runningPcb

    @runningPCB.setter
    def runningPCB(self, pcb):
        self._runningPcb = pcb

    def add(self, pcb):
        self._tabla.append(pcb)

    def remove(self, pid):
        pcb = self.get(pid)
        self._tabla.remove(pcb)

    def get(self, pidBuscado):
        pcbResultado = None
        for pcb in self._tabla:
            if pcb.pid == pidBuscado:
                pcbResultado = pcb
                break
        return  pcbResultado

    def getNewPID(self):
        nuevoPid = self.pid + 1
        self.pid = nuevoPid
        return nuevoPid

################################ DISPATCHER ########################################


class Dispatcher:

    def load(self, pcb):
        HARDWARE.timer.reset()
        HARDWARE.cpu.pc = pcb.pc
        HARDWARE.mmu.baseDir = pcb.baseDir
        log.logger.info("loading pcb:{pcb}".format(pcb=pcb))

    def save(self, pcb):
        pcb.pc = HARDWARE.cpu.pc
        HARDWARE.cpu.pc = -1
        log.logger.info("saving pcb:{pcb}".format(pcb=pcb))

################################ KERNEL ########################################
# emulates the core of an Operative System


class Kernel:

    def __init__(self, seleccion, quantum):
        if seleccion == "1":
            scheduler = PriorityExpropiativoScheduler()
        if seleccion == "2":
            scheduler = PriorityNoExpropiativoScheduler()
        if seleccion == "3":
            scheduler = FCFSScheduler()
        if seleccion == "4":
            scheduler = RoundRobinScheduler(int(quantum))

        ## setup interruption handlers
        killHandler = KillInterruptionHandler(self)
        HARDWARE.interruptVector.register(KILL_INTERRUPTION_TYPE, killHandler)

        ioInHandler = IoInInterruptionHandler(self)
        HARDWARE.interruptVector.register(IO_IN_INTERRUPTION_TYPE, ioInHandler)

        ioOutHandler = IoOutInterruptionHandler(self)
        HARDWARE.interruptVector.register(IO_OUT_INTERRUPTION_TYPE, ioOutHandler)

        newHandler = NewInterruptionHandler(self)
        HARDWARE.interruptVector.register(NEW_INTERRUPTION_TYPE, newHandler)

        timeoutHandler = TimeoutInterruptionHandle(self)
        HARDWARE.interruptVector.register(TIMEOUT_INTERRUPTION_TYPE, timeoutHandler)


        ## controls the Hardware's I/O Device
        self._ioDeviceController = IoDeviceController(HARDWARE.ioDevice)
        self._loader = Loader()
        self._pcbTable = PCBTable()
        self._dispatcher = Dispatcher()
        self._scheduler = scheduler

    @property
    def ioDeviceController(self):
        return self._ioDeviceController

    @property
    def loader(self):
        return self._loader

    @property
    def pcbTable(self):
        return self._pcbTable

    @property
    def dispatcher(self):
        return self._dispatcher

    @property
    def scheduler(self):
        return self._scheduler

    ## emulates a "system call" for programs execution
    def run(self, program, priority):
        tuple = [program, priority]
        newIRQ = IRQ(NEW_INTERRUPTION_TYPE, tuple)
        HARDWARE.interruptVector.handle(newIRQ)
        log.logger.info("\n Executing program: {name}".format(name=program.name))
        log.logger.info(HARDWARE)

    def __repr__(self):
        return "Kernel "


class GraficadorGant():
    def __init__(self, kernel):
        self._kernel = kernel
        self._representacion = []
        self._headers = ["procesos"]

    @property
    def representacion(self, representacion):
        return self._representacion

    @representacion.setter
    def representacion(self, representacion):
        self._representacion = representacion

    @property
    def kernel(self):
        return self._kernel

    def tick(self, ticknum):
        if ticknum == 1:
            self.representacion = self.cuadro(self.kernel.pcbTable.tabla)
            self.actualizarRepresentacion(ticknum, self.kernel.pcbTable.tabla)

        if ticknum > 1:
            self.actualizarRepresentacion(ticknum, self._kernel.pcbTable.tabla)
        if HARDWARE.cpu.isBusy():
            log.logger.info(self.__repr__())

    def actualizarRepresentacion(self, ticknum, pcbTable):
        self._headers.append(ticknum)

        nroProceso = 0

        for pcb in pcbTable:
            retorna = pcb.state
            self._representacion[nroProceso].append(retorna)

            nroProceso = nroProceso + 1

    def cuadro(self, pcbTable):
        lista = []

        for pcb in pcbTable:
            lista.append([pcb.path])
        return lista


    def __repr__(self):
        return tabulate(self._representacion, headers= self._headers, tablefmt='grid', stralign ='center')