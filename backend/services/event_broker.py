import asyncio
import json
import traceback
from typing import Dict, List, Callable, Any, Coroutine
from backend.config import settings

class EventBroker:
    def __init__(self):
        self.mode = settings.RUN_MODE
        self.subscribers: Dict[str, List[Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]]] = {}
        
        # Local Mode structures
        self.queue = asyncio.Queue()
        self.worker_task = None
        
        # Production Mode structures
        self.kafka_producer = None
        self.consumer_tasks: List[asyncio.Task] = []

    async def start(self):
        """Starts the event broker (starts background queue listener or Kafka producer)."""
        if self.mode == "local":
            self.worker_task = asyncio.create_task(self._local_worker_loop())
            print("Local Event Broker started (in-memory queue).")
        else:
            try:
                from aiokafka import AIOKafkaProducer
                self.kafka_producer = AIOKafkaProducer(
                    bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                    value_serializer=lambda v: json.dumps(v).encode('utf-8')
                )
                await self.kafka_producer.start()
                print(f"Kafka Event Broker started. Connected to {settings.KAFKA_BOOTSTRAP_SERVERS}")
            except Exception as e:
                print(f"Failed to connect to Kafka: {e}. Falling back to Local Event Broker.")
                self.mode = "local"
                await self.start()

    async def stop(self):
        """Gracefully shuts down event loops, consumers, and producers."""
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
                
        if self.kafka_producer:
            await self.kafka_producer.stop()
            
        for task in self.consumer_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
                
        print("Event Broker stopped.")

    async def publish(self, topic: str, payload: Dict[str, Any]):
        """Publishes an event to the broker under a specific topic/key."""
        event = {
            "topic": topic,
            "payload": payload
        }
        
        if self.mode == "local":
            await self.queue.put(event)
        else:
            try:
                if self.kafka_producer:
                    # Publish to Kafka topic
                    await self.kafka_producer.send_and_wait(topic, payload)
                else:
                    raise Exception("Kafka Producer is not initialized.")
            except Exception as e:
                print(f"Error publishing to Kafka topic '{topic}': {e}. Using local queue fallback.")
                # Fallback to local queue
                await self.queue.put(event)

    def subscribe(self, topic: str, callback: Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]):
        """Registers a coroutine callback function to listen for events on a specific topic."""
        if topic not in self.subscribers:
            self.subscribers[topic] = []
        self.subscribers[topic].append(callback)
        
        # For production mode, start a separate consumer thread per unique subscription
        if self.mode == "production":
            task = asyncio.create_task(self._kafka_consumer_loop(topic, callback))
            self.consumer_tasks.append(task)
            print(f"Registered Kafka consumer subscription for topic: {topic}")
        else:
            print(f"Registered Local subscription for topic: {topic}")

    async def _local_worker_loop(self):
        """Background loop reading from local queue and executing matching subscriber callbacks."""
        try:
            while True:
                event = await self.queue.get()
                topic = event.get("topic")
                payload = event.get("payload")
                
                if topic in self.subscribers:
                    for callback in self.subscribers[topic]:
                        try:
                            # Invoke asynchronously
                            await callback(payload)
                        except Exception as e:
                            print(f"Error executing callback for topic {topic}: {e}")
                            traceback.print_exc()
                            
                self.queue.task_done()
        except asyncio.CancelledError:
            pass

    async def _kafka_consumer_loop(self, topic: str, callback: Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]):
        """Background consumer loop pulling messages from Kafka broker and invoking callbacks."""
        from aiokafka import AIOKafkaConsumer
        consumer = AIOKafkaConsumer(
            topic,
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            value_deserializer=lambda m: json.loads(m.decode('utf-8'))
        )
        try:
            await consumer.start()
            async for msg in consumer:
                try:
                    await callback(msg.value)
                except Exception as e:
                    print(f"Error processing Kafka event in callback for topic '{topic}': {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Error in Kafka consumer loop for topic '{topic}': {e}")
        finally:
            await consumer.stop()

event_broker = EventBroker()
